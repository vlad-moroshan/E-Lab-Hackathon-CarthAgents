"""Notebook-friendly selection, execution and evaluation with separated ground truth."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Callable
from uuid import uuid4

from carth.ingest import ingest
from carth.output.check import check_document
from carth.output.validate import validation_errors

Extractor = Callable[[dict, str], dict]


@dataclass(frozen=True)
class Sample:
    doc_id: str
    source: Path


def select_inputs(root: Path, pattern: str = "**/*", suffixes: tuple[str, ...] = (".pdf", ".xlsx"),
                  limit: int | None = None) -> list[Sample]:
    """Discover documents from filenames only. Never read keys to select an extraction input."""
    root = Path(root)
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive or None")
    paths = sorted(p for p in root.glob(pattern) if p.is_file() and p.suffix.lower() in suffixes
                   and not p.name.startswith("~$") and not any(part.startswith((".", "_")) for part in p.relative_to(root).parts))
    if limit is not None:
        paths = paths[:limit]
    if not paths:
        raise ValueError(f"no input documents selected in {root}")
    ids = [p.stem for p in paths]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate document IDs in selection; use a narrower input set")
    return [Sample(p.stem, p.resolve()) for p in paths]


def load_evidence(samples: list[Sample], loader: Callable = ingest) -> dict[str, dict]:
    return {sample.doc_id: loader(sample.source) for sample in samples}


def token_preview(evidence: dict, limit: int = 30) -> list[dict]:
    return [{k: t[k] for k in ("id", "sheet", "cell", "page", "text", "bbox") if k in t}
            for t in evidence["tokens"][:limit]]


@dataclass
class Run:
    directory: Path
    samples: list[Sample]
    outputs: dict[str, dict[str, dict]]
    metrics: list[dict]


def run_experiment(samples: list[Sample], algorithms: dict[str, Extractor], *, evidence: dict[str, dict] | None = None,
                   output_root: Path = Path("out/experiments"), preprocessors: tuple[Callable, ...] = ()) -> Run:
    """Each algorithm gets its own evidence copy; validate before saving or evaluation."""
    if not samples or not algorithms:
        raise ValueError("select at least one document and one algorithm")
    if len({s.doc_id for s in samples}) != len(samples):
        raise ValueError("duplicate document IDs")
    for name in algorithms:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError(f"unsafe algorithm name: {name!r}")
    for sample in samples:
        if not re.fullmatch(r"[A-Za-z0-9_. -]+", sample.doc_id) or sample.doc_id in {".", ".."}:
            raise ValueError(f"unsafe document ID: {sample.doc_id!r}")
    import copy

    evidence = evidence if evidence is not None else load_evidence(samples)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    directory = Path(output_root) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    outputs, metrics = {}, []
    for name, algorithm in algorithms.items():
        pred_dir = directory / name / "pred"
        pred_dir.mkdir(parents=True)
        outputs[name] = {}
        for sample in samples:
            start = perf_counter()
            prepared = copy.deepcopy(evidence[sample.doc_id])
            for step in preprocessors:
                prepared = step(prepared)
            document = algorithm(prepared, sample.doc_id)
            errors = validation_errors(document)
            if not errors and document["meta"]["doc_id"] != sample.doc_id:
                errors = ["algorithm changed the document ID"]
            if errors:
                raise ValueError(f"{name}/{sample.doc_id}: " + "; ".join(errors[:5]))
            (pred_dir / f"{sample.doc_id}.pred.json").write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
            outputs[name][sample.doc_id] = document
            metrics.append({"algorithm": name, "doc_id": sample.doc_id, "seconds": round(perf_counter()-start, 3),
                            "rows": len(document["rows"]), "observed": sum(v["status"] == "observed" for r in document["rows"] for v in r["fields"].values()),
                            "check_errors": check_document(document, sample.source, evidence[sample.doc_id])})
    manifest = {"inputs": [{"doc_id": s.doc_id, "source": str(s.source), "sha256": hashlib.sha256(s.source.read_bytes()).hexdigest()} for s in samples],
                "algorithms": list(algorithms), "metrics": metrics}
    (directory / "run.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    return Run(directory, samples, outputs, metrics)


def evaluate_run(run: Run) -> dict:
    """Ground truth is opened only here, after predictions have been produced."""
    from carth.eval.score import score_doc

    details, missing = [], []
    for sample in run.samples:
        key_path = sample.source.with_suffix(".key.json")
        if not key_path.exists():
            missing.append(sample.doc_id)
            continue
        key = json.loads(key_path.read_text(encoding="utf-8"))
        if key["meta"]["doc_id"] != sample.doc_id:
            raise ValueError(f"ground-truth document ID mismatch: {key_path}")
        for name, outputs in run.outputs.items():
            result = score_doc(key_path, key, outputs[sample.doc_id])
            details.append({"algorithm": name, **asdict(result), "score": result.score})
    summary = []
    for name in run.outputs:
        rows = [d for d in details if d["algorithm"] == name]
        totals = {k: sum(d[k] for d in rows) for k in ("total", "right", "wrong", "blank", "extra", "score")}
        summary.append({"algorithm": name, "evaluated_documents": len(rows), **totals})
    result = {"summary": summary, "documents": details, "missing_keys": missing}
    (run.directory / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    return result
