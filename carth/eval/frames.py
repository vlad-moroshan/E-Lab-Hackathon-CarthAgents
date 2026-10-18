"""Evaluation-only coordinate frames for scans.

Our pointers are on the page as given. The corpus keys give scan boxes on the original *print*, before the scanner
turned single pages (f06_03: one page upside down, one sideways). To compare, the evaluator picks per page the turn
(0 / 90 / 180 / 270, counter-clockwise, y down) that puts the most reference boxes inside key rows. This is an
accommodation to the generator's convention (open question Q4), kept out of extraction on purpose.
"""

from __future__ import annotations

TURNS = (0, 90, 180, 270)


def turn_box(b, turn: int, W: float, H: float) -> list:
    """Box on a W x H page -> box on that page turned `turn` degrees counter-clockwise (PIL rotate, expand=True)."""
    pts = [(b[0], b[1]), (b[2], b[3])]
    if turn == 90:
        pts = [(y, W - x) for x, y in pts]
    elif turn == 180:
        pts = [(W - x, H - y) for x, y in pts]
    elif turn == 270:
        pts = [(H - y, x) for x, y in pts]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def centre_in(b, row, pad: float = 0.5) -> bool:
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return row[0] - pad <= cx <= row[2] + pad and row[1] - pad <= cy <= row[3] + pad


def best_turn(boxes: list, rows: list, W: float, H: float) -> int:
    """The turn that puts the most `boxes` inside any of `rows` (ties prefer no turn)."""
    def hits(t):
        return sum(any(centre_in(turn_box(b, t, W, H), r) for r in rows) for b in boxes)
    return max(TURNS, key=lambda t: (hits(t), t == 0))
