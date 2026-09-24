"""How close an inbound text is to each open request.

Used only when a sender could be answering more than one live request. A
single candidate is not scored: that text is a reply. None is a new request.

The score is cosine similarity of embeddings. "I just sharpened it" sits near
"does anyone have a saw" and far from "you can borrow my bicycle", which
shared words cannot show. This module does not call a model. The caller
supplies the vectors.
"""

from __future__ import annotations

# How far the best score must lead the next one before we trust it.
ASSOCIATION_MARGIN = 0.08
# Below this, the text does not associate with that request.
ASSOCIATION_FLOOR = 0.35

AWAITING_CHOICE = "awaiting_choice"
CHOICE_RECEIVED = "choice_received"
CHOICE_UNRECOGNIZED = "choice_unrecognized"

NEW_REQUEST_LETTER = "N"
NEW_REQUEST_LABEL = "This is a new request"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine of two vectors. Mismatched or empty vectors score 0."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / ((left_norm ** 0.5) * (right_norm ** 0.5))


def leading_request(scores: list[tuple[int, float]]) -> int | None:
    """The request id that clearly wins, or None when the weigh is low.

    Low means the best score is under the floor, or it does not lead the
    next score by ``ASSOCIATION_MARGIN``.
    """
    if not scores:
        return None
    ordered = sorted(scores, key=lambda item: item[1], reverse=True)
    best_id, best = ordered[0]
    if best < ASSOCIATION_FLOOR:
        return None
    if len(ordered) > 1 and best - ordered[1][1] < ASSOCIATION_MARGIN:
        return None
    return best_id


def choice_letters(count: int) -> list[str]:
    """A through M, at most 13 request choices.

    N is reserved for "this is a new request", so the loop stops when it
    would emit N. A 14th open request is not given a letter. Callers zip
    this list with the candidate list, so anything past M is left out of
    the question rather than colliding with N.
    """
    letters: list[str] = []
    for offset in range(count):
        letter = chr(ord("A") + offset)
        if letter == NEW_REQUEST_LETTER:
            break
        letters.append(letter)
    return letters


def clarification_question(options: list[tuple[str, str]]) -> str:
    """The canned question. ``options`` is ``(letter, label)`` in order."""
    lines = ["Which request is this about? Reply with a letter only."]
    for letter, label in options:
        lines.append(f"{letter}) {label}")
    return "\n".join(lines)


def parse_choice(body: str, letters: set[str]) -> str | None:
    """A body that is only a choice letter, or None."""
    token = (body or "").strip().upper().rstrip(").")
    if token in letters:
        return token
    return None


def candidate_label(*, summary: str | None, original_body: str | None, request_id: int) -> str:
    """Summary, else the first line of the original text, else a bare id."""
    text = (summary or "").strip()
    if not text and original_body:
        text = original_body.strip().splitlines()[0].strip()
    if not text:
        text = f"Request {request_id}"
    return text[:140]
