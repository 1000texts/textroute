from src.domain.association import (
    ASSOCIATION_FLOOR,
    choice_letters,
    clarification_question,
    cosine_similarity,
    leading_request,
    parse_choice,
)


def test_sharpened_is_closer_to_a_saw_than_a_bicycle():
    saw = [1.0, 0.0]
    bicycle = [0.0, 1.0]
    sharpened = [0.9, 0.1]
    assert cosine_similarity(sharpened, saw) > cosine_similarity(sharpened, bicycle)


def test_leading_request_rejects_a_close_call_and_a_weak_score():
    assert leading_request([(1, 0.9), (2, 0.2)]) == 1
    assert leading_request([(1, 0.5), (2, 0.48)]) is None
    assert leading_request([(1, ASSOCIATION_FLOOR - 0.01)]) is None


def test_choice_letters_stop_before_n():
    """N means a new request, so request choices are A through M only."""
    letters = choice_letters(20)
    assert letters == list("ABCDEFGHIJKLM")
    assert len(letters) == 13
    assert "N" not in letters


def test_question_and_letter_parsing():
    text = clarification_question([("A", "Borrow a saw"), ("N", "This is a new request")])
    assert "A) Borrow a saw" in text
    assert "Reply with a letter only." in text
    assert parse_choice("a", {"A", "N"}) == "A"
    assert parse_choice("yes", {"A", "N"}) is None
