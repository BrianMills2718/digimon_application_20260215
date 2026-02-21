from eval.benchmark import _parse_llm_judge_correct


def test_parse_fenced_false_json() -> None:
    payload = """```json
{"correct": false, "reason": "wrong answer"}
```"""
    assert _parse_llm_judge_correct(payload) is False


def test_parse_fenced_true_json() -> None:
    payload = """```json
{"correct": true, "reason": "matches gold"}
```"""
    assert _parse_llm_judge_correct(payload) is True


def test_parse_embedded_false_json_span() -> None:
    payload = "Judge result follows: {\"correct\": false, \"reason\": \"not enough\"} Thanks."
    assert _parse_llm_judge_correct(payload) is False


def test_parse_text_incorrect_is_false() -> None:
    payload = "INCORRECT: predicted answer does not match."
    assert _parse_llm_judge_correct(payload) is False


def test_parse_text_correct_is_true() -> None:
    payload = "correct"
    assert _parse_llm_judge_correct(payload) is True
