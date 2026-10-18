"""Pages without a text layer (scans, glyphs-as-outlines) -> word tokens, same schema as pdf_text.

Pipeline per page: render (pypdfium2, scale = dpi/72, so pixel / scale = PDF points of the page as given)
-> orientation (PaddleOCR's PP-LCNet doc orientation model; its label L means "turn L° counter-clockwise to be
upright") -> we turn the image ourselves (exact, invertible) -> OCR engine on the upright image -> each word box is
mapped back to original page coordinates (`bbox`) and kept in the upright frame (`rbox`).

Engines (optional extras, CPU supported): "paddle" (PP-OCR, word boxes),
"doctr" (db_resnet50 + parseq, word boxes), "tesseract" (deu, word boxes). The bake-off picks one with `carth recall`.
OCR by a model is allowed (organiser answer Q5); code still parses every amount from the token text.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from carth.numbers import parse_amount

import numpy as np
import pypdfium2 as pdfium

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


# ---------------------------------------------------------------------------------------------------- geometry


def to_page(box, angle: int, W: float, H: float):
    """Box [x0, y0, x1, y1] in the upright image -> box in the original image (size W x H), for an upright image
    made by PIL `img.rotate(angle, expand=True)` (counter-clockwise, y down)."""
    pts = [(box[0], box[1]), (box[2], box[3])]
    if angle == 90:
        pts = [(W - v, u) for u, v in pts]
    elif angle == 180:
        pts = [(W - u, H - v) for u, v in pts]
    elif angle == 270:
        pts = [(v, H - u) for u, v in pts]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


# ---------------------------------------------------------------------------------------------------- engines


class Paddle:
    name = "paddle"

    def __init__(self, lang: str = "de", device: str | None = None, size: str = "medium"):
        """size: PP-OCRv6 model size, "tiny" | "small" | "medium" (speed vs accuracy, see docs/IMPLEMENTATION.md)."""
        from paddleocr import DocImgOrientationClassification, PaddleOCR

        kw = {"device": device} if device else {}
        self.clf = DocImgOrientationClassification(model_name="PP-LCNet_x1_0_doc_ori", **kw)
        self.ocr = PaddleOCR(text_detection_model_name=f"PP-OCRv6_{size}_det",
                             text_recognition_model_name=f"PP-OCRv6_{size}_rec", use_doc_orientation_classify=False,
                             use_doc_unwarping=False, use_textline_orientation=False, return_word_box=True, **kw)

    def orientation(self, img) -> tuple[int, float]:
        r = self.clf.predict(np.array(img.convert("RGB")))[0].json["res"]
        return int(r["label_names"][0]), float(r["scores"][0])

    def words(self, img) -> list[tuple[str, list, float]]:
        """Paddle splits a line into pieces at spaces *and* punctuation ("40.414", ",", "97"); a word is the run of
        pieces between two " " pieces, its box the union of theirs."""
        d = self.ocr.predict(np.array(img.convert("RGB")))[0].json["res"]
        out = []
        for pieces, boxes, score in zip(d["text_word"], d["text_word_boxes"], d["rec_scores"]):
            run: list = []
            for w, b in [*zip(pieces, boxes), (" ", None)]:
                if w.strip():
                    run.append((w, b))
                    continue
                if run:
                    bs = [r[1] for r in run]
                    out.append(("".join(r[0] for r in run), [float(min(x[0] for x in bs)), float(min(x[1] for x in bs)),
                                                             float(max(x[2] for x in bs)), float(max(x[3] for x in bs))],
                                float(score)))
                run = []
        return out


class Doctr:
    name = "doctr"

    def __init__(self, **_):
        from doctr.models import ocr_predictor

        self.model = ocr_predictor(det_arch="db_resnet50", reco_arch="parseq", pretrained=True,
                                   assume_straight_pages=True)

    def words(self, img) -> list[tuple[str, list, float]]:
        W, H = img.size
        page = self.model([np.array(img.convert("RGB"))]).pages[0]
        return [(w.value, [w.geometry[0][0] * W, w.geometry[0][1] * H, w.geometry[1][0] * W, w.geometry[1][1] * H],
                 float(w.confidence)) for b in page.blocks for ln in b.lines for w in ln.words]


class Tesseract:
    name = "tesseract"

    def __init__(self, psm: int = 6, **_):
        """psm: Tesseract page segmentation mode; 6 = one uniform block, 11 = sparse text (often better for tables)."""
        import pytesseract

        self.t, self.psm = pytesseract, psm

    def words(self, img) -> list[tuple[str, list, float]]:
        d = self.t.image_to_data(img, lang="deu", config=f"--psm {self.psm}", output_type=self.t.Output.DICT)
        return [(s, [x, y, x + w, y + h], c / 100) for s, x, y, w, h, c in
                zip(d["text"], d["left"], d["top"], d["width"], d["height"], d["conf"]) if s.strip() and c >= 0]


ENGINES = {"paddle": Paddle, "doctr": Doctr, "tesseract": Tesseract}
_orient: Paddle | None = None  # the orientation model is Paddle's, shared by every engine


def _orientation(img) -> tuple[int, float]:
    """Paddle's page-orientation model when installed; without it the page is read both upright and turned 180°
    and the better reading wins (sideways pages need the model)."""
    global _orient
    if _orient is None:
        try:
            from paddleocr import DocImgOrientationClassification

            _orient = type("O", (), {})()
            _orient.clf = DocImgOrientationClassification(model_name="PP-LCNet_x1_0_doc_ori")
        except Exception:  # paddle runtime not installed: no orientation model
            _orient = False
    if _orient is False:  # no model: OCR upright and upside down, reading quality decides (see ocr_pages)
        return 180, 0.0
    return Paddle.orientation(_orient, img)


# ---------------------------------------------------------------------------------------------------- pages


def ocr_pages(path, engine, pages: list[int], dpi: int = 300) -> list[dict]:
    """OCR the given 1-based pages of a PDF. Returns tokens in the pdf_text schema.

    Every page is handled on its own, so a token's boxes never depend on which other pages were processed:
      `bbox`  - on the page as given (points, top-left origin): the pointer
      `rbox`  - in the upright frame of that page (points): what line / column grouping uses
      `angle` - the counter-clockwise turn that made the page upright; `dir` = text direction on the page as given
    When the orientation model says the page is turned, or is unsure (conf < 0.5), both its angle and 0 are OCRed and
    the reading with the stronger bounded confidence/amount quality wins; `orient_conf` keeps the doubt visible to later checks.
    Note: the corpus keys give scan boxes on the original *print*; matching our page-as-given boxes against them
    is an evaluation concern (carth/eval/frames.py), not something extraction should bake in.
    """
    pdf = pdfium.PdfDocument(str(path))
    s = dpi / 72
    out = []
    for pno in pages:
        img = pdf[pno - 1].render(scale=s, grayscale=True).to_pil()
        W, H = img.size
        angle, conf = engine.orientation(img) if hasattr(engine, "orientation") else _orientation(img)
        classifier_angle = angle
        # a turned page is the exception: the model has called upright fax pages "90°" with high confidence, so any
        # non-zero (or unsure) call is checked against reading the page as given
        tries = [angle] if conf >= 0.5 and angle == 0 else list(dict.fromkeys([angle, 0]))
        best = None
        qualities = {}
        for a in tries:
            words = engine.words(img.rotate(a, expand=True) if a else img)
            quality = reading_quality(words)
            qualities[a] = round(quality, 4)
            if best is None or quality > best[0]:
                best = (quality, a, words)
        quality, angle, words = best
        ordered = sorted(qualities.values(), reverse=True)
        margin = ordered[0] - ordered[1] if len(ordered) > 1 else quality
        for text, box, score in words:
            pb = to_page(box, angle, W, H)
            out.append({"page": pno, "text": text, "bbox": [round(v / s, 2) for v in pb],
                        "rbox": [round(v / s, 2) for v in box], "dir": (360 - angle) % 360, "upright": angle == 0,
                        "size": round((box[3] - box[1]) / s, 2), "bold": False, "src": f"ocr:{engine.name}",
                        "conf": round(score, 4), "angle": angle, "orient_conf": round(conf, 3),
                        "classifier_angle": classifier_angle,
                        "orientation_quality": round(quality, 4), "orientation_candidates": qualities,
                        "orientation_margin": round(margin, 4), "orientation_uncertain": margin < .1 if len(qualities) > 1 else conf < .5})
    return out


def reading_quality(words):
    """Bounded confidence/amount quality; duplicates and fragment count cannot dominate a clean reading."""
    unique = {(text.strip(), tuple(box)): (text.strip(), conf) for text, box, conf in words if text.strip()}
    values = list(unique.values())
    if not values:
        return 0.0
    mean = sum(max(0, min(1, conf)) for _, conf in values) / len(values)
    numeric = sum(conf for text, conf in values if parse_amount(text) is not None) / len(values)
    return .7 * mean + .3 * numeric


# ---------------------------------------------------------------------------------------------------- parallel

PER_WORKER_GB = 6.5  # measured peak RSS of one Paddle "small" worker at 300 dpi (docs/IMPLEMENTATION.md)
_ENGINE = None


def auto_workers(per_worker_gb: float = PER_WORKER_GB) -> int:
    """Conservative portable default; explicit --workers overrides require a measured memory budget."""
    # Without a portable available-memory estimate, one worker is the conservative default.
    return 1


def _init(name: str, kw: dict) -> None:
    global _ENGINE
    _ENGINE = ENGINES[name](**kw)


def _job(path: str, pages: list[int], dpi: int):
    t0 = time.time()
    return path, ocr_pages(path, _ENGINE, pages, dpi), time.time() - t0


def ocr_many(jobs: list[tuple[str, list[int]]], engine: str = "paddle", engine_kw: dict | None = None,
             dpi: int = 300, workers: int | None = None):
    """Yield (path, tokens, seconds) per document as workers finish. One engine per worker process; the largest
    documents go first so the pool stays busy."""
    jobs = sorted(jobs, key=lambda j: -len(j[1]))
    workers = workers or auto_workers()
    with ProcessPoolExecutor(max_workers=min(workers, len(jobs) or 1), initializer=_init,
                             initargs=(engine, engine_kw or {})) as pool:
        futs = {pool.submit(_job, str(path), pages, dpi): str(path) for path, pages in jobs}
        for f in as_completed(futs):
            try:
                yield f.result()
            except BrokenProcessPool as exc:
                yield futs[f], {"error": str(exc), "scope": "worker_pool"}, 0.0
            except Exception as exc:
                yield futs[f], {"error": f"{type(exc).__name__}: {exc}", "scope": "document"}, 0.0
