from __future__ import annotations

from council.llm_transport import extract_json_object, load_json_object


def test_extract_json_object_handles_real_triple_backtick_fences():
    payload = 'prefix ```json\n{"verdict":"PASS","confidence":0.8}\n``` suffix'

    assert extract_json_object(payload) == '{"verdict":"PASS","confidence":0.8}'
    assert load_json_object(payload) == {"verdict": "PASS", "confidence": 0.8}


def test_extract_json_object_handles_sentinel_fences():
    payload = (
        "prefix [TRIPLE_BACKTICK]json\n"
        '{"verdict":"PASS","reasoning":"ok"}\n'
        "[TRIPLE_BACKTICK] suffix"
    )

    assert extract_json_object(payload) == '{"verdict":"PASS","reasoning":"ok"}'
    assert load_json_object(payload) == {"verdict": "PASS", "reasoning": "ok"}
