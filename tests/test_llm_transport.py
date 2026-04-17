from __future__ import annotations

from types import SimpleNamespace

import pytest

from council.llm_transport import extract_json_object, load_json_object


def test_extract_json_object_handles_plain_json_no_fence():
    assert extract_json_object('{"verdict":"PASS"}') == '{"verdict":"PASS"}'


def test_extract_json_object_handles_json_with_surrounding_prose():
    payload = 'Sure, here is the verdict: {"verdict":"PASS","confidence":0.9} thanks!'
    assert extract_json_object(payload) == '{"verdict":"PASS","confidence":0.9}'


def test_extract_json_object_returns_none_when_no_object_present():
    assert extract_json_object("no JSON here, just prose.") is None
    assert extract_json_object("") is None


def test_load_json_object_returns_none_for_unparseable():
    assert load_json_object("not json at all") is None


def test_load_json_object_returns_none_for_non_object_root():
    # Array roots should be rejected — Chair and reviewers require object payloads.
    assert load_json_object("[1, 2, 3]") is None


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


@pytest.mark.asyncio
async def test_invoke_json_completion_uses_response_format_first():
    from council.llm_transport import invoke_json_completion

    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdict":"PASS"}'))],
            usage=SimpleNamespace(total_tokens=17),
        )

    result = await invoke_json_completion(
        model="openai/gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        timeout=10,
        temperature=0.1,
        acompletion_func=fake_acompletion,
    )

    assert result.output_mode == "response_format"
    assert result.tokens_used == 17
    assert calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_invoke_json_completion_falls_back_when_response_format_rejected():
    from council.llm_transport import invoke_json_completion

    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("response_format is not supported by this model")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdict":"PASS"}'))],
            usage=SimpleNamespace(total_tokens=9),
        )

    result = await invoke_json_completion(
        model="google/gemini-2.5-pro",
        messages=[{"role": "user", "content": "hello"}],
        timeout=10,
        temperature=0.1,
        acompletion_func=fake_acompletion,
    )

    assert result.output_mode == "prompt_json_fallback"
    assert "response_format" not in calls[1]


@pytest.mark.asyncio
async def test_invoke_json_completion_reraises_non_transport_errors():
    from council.llm_transport import invoke_json_completion

    async def fake_acompletion(**kwargs):
        raise TimeoutError("upstream timeout")

    with pytest.raises(TimeoutError, match="upstream timeout"):
        await invoke_json_completion(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
            timeout=10,
            temperature=0.1,
            acompletion_func=fake_acompletion,
        )


def test_extract_json_object_handles_braces_inside_quoted_strings():
    # Braces inside string values must not confuse the depth counter.
    payload = '{"key": "value with { braces } inside", "ok": true}'
    assert extract_json_object(payload) == payload


def test_extract_json_object_handles_nested_objects():
    payload = '{"outer": {"inner": {"deep": 1}}, "x": 2}'
    assert extract_json_object(payload) == payload


def test_extract_json_object_returns_first_object_when_multiple_present():
    payload = '{"first": 1} some text {"second": 2}'
    assert extract_json_object(payload) == '{"first": 1}'


def test_extract_json_object_handles_fenced_block_no_language_tag():
    bt = chr(96) * 3
    payload = f"here {bt}\n{{\"verdict\":\"PASS\"}}\n{bt} done"
    assert extract_json_object(payload) == '{"verdict":"PASS"}'
