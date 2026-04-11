from __future__ import annotations

from types import SimpleNamespace

import pytest

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
