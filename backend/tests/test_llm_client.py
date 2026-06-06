"""
Unit tests for LLMClient.structured_completion().

litellm.acompletion is mocked so no real API calls are made.
Tests cover:
  1. Success on first attempt
  2. Retry: fails twice, succeeds on 3rd attempt
  3. All 3 attempts fail → RuntimeError raised
  4. Fallback: primary fails all 3 → fallback model succeeds
  5. Fallback: primary fails all 3 → fallback also fails → RuntimeError
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel

from app.core.llm import LLMClient


# Minimal Pydantic schema used across all tests
class SimpleSchema(BaseModel):
    answer: str


def make_mock_response(content: str) -> MagicMock:
    """
    Build a fake litellm response object that matches the shape
    LLMClient reads: response.choices[0].message.content and response.usage.
    """
    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage

    return response


# ---------------------------------------------------------------------------
# Test 1 — success on first attempt
# ---------------------------------------------------------------------------

async def test_success_on_first_attempt():
    """
    When acompletion returns valid JSON on the first call,
    structured_completion should return the parsed schema and call acompletion once.
    """
    client = LLMClient()
    mock_response = make_mock_response('{"answer": "hello"}')

    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
        result = await client.structured_completion(
            prompt="Say hello",
            schema=SimpleSchema,
            agent_name="test_agent",
        )

    # Result is correctly parsed into the schema
    assert isinstance(result, SimpleSchema)
    assert result.answer == "hello"

    # acompletion was called exactly once — no unnecessary retries
    assert mock_call.call_count == 1


# ---------------------------------------------------------------------------
# Test 2 — retry: fail twice, succeed on 3rd attempt
# ---------------------------------------------------------------------------

async def test_retry_succeeds_on_third_attempt():
    """
    When acompletion raises on attempts 1 and 2 but succeeds on attempt 3,
    structured_completion should return the result and call acompletion exactly 3 times.
    """
    client = LLMClient()
    mock_response = make_mock_response('{"answer": "recovered"}')

    # side_effect list: first two calls raise, third call returns a valid response
    mock_call = AsyncMock(side_effect=[
        RuntimeError("transient error on attempt 1"),
        RuntimeError("transient error on attempt 2"),
        mock_response,
    ])

    with patch("litellm.acompletion", new=mock_call):
        result = await client.structured_completion(
            prompt="test prompt",
            schema=SimpleSchema,
            agent_name="test_agent",
        )

    # Result from the 3rd attempt is returned correctly
    assert isinstance(result, SimpleSchema)
    assert result.answer == "recovered"

    # All 3 attempts were made
    assert mock_call.call_count == 3


# ---------------------------------------------------------------------------
# Test 3 — all 3 attempts fail → RuntimeError
# ---------------------------------------------------------------------------

async def test_all_attempts_fail_raises_runtime_error():
    """
    When all 3 primary attempts raise, the fallback is also tried once.
    Since this mock raises on every call, both primary and fallback fail.
    structured_completion should:
      - raise RuntimeError with 'fallback_error' in the message
      - have called acompletion exactly 4 times (3 primary + 1 fallback)
    """
    client = LLMClient()

    # Every call raises — covers both the 3 primary attempts and the 1 fallback attempt
    mock_call = AsyncMock(side_effect=RuntimeError("persistent api error"))

    with patch("litellm.acompletion", new=mock_call):
        # Error message now includes 'fallback_error' because fallback was also tried
        with pytest.raises(RuntimeError, match="fallback_error"):
            await client.structured_completion(
                prompt="test prompt",
                schema=SimpleSchema,
                agent_name="test_agent",
            )

    # 3 primary attempts + 1 fallback attempt = 4 total calls
    assert mock_call.call_count == 4


# ---------------------------------------------------------------------------
# Test 4 — fallback: primary fails all 3 → fallback model succeeds
# ---------------------------------------------------------------------------

async def test_fallback_succeeds_when_primary_exhausted():
    """
    When the primary model fails all 3 retries, LLMClient should try the
    fallback model (_FALLBACK_MODEL) once. If the fallback succeeds, the
    result is returned normally — the caller does not know a fallback was used.

    acompletion call count should be 4 total: 3 primary attempts + 1 fallback.
    """
    client = LLMClient()
    fallback_response = make_mock_response('{"answer": "from fallback"}')

    # First 3 calls (primary model) raise, 4th call (fallback model) succeeds
    mock_call = AsyncMock(side_effect=[
        RuntimeError("primary fail 1"),  # attempt 1 on primary
        RuntimeError("primary fail 2"),  # attempt 2 on primary
        RuntimeError("primary fail 3"),  # attempt 3 on primary
        fallback_response,               # fallback model succeeds
    ])

    with patch("litellm.acompletion", new=mock_call):
        result = await client.structured_completion(
            prompt="test prompt",
            schema=SimpleSchema,
            agent_name="test_agent",
        )

    # Fallback result is returned correctly
    assert isinstance(result, SimpleSchema)
    assert result.answer == "from fallback"

    # 3 primary attempts + 1 fallback attempt = 4 total calls
    assert mock_call.call_count == 4


# ---------------------------------------------------------------------------
# Test 5 — fallback: primary fails all 3 → fallback also fails → RuntimeError
# ---------------------------------------------------------------------------

async def test_fallback_fails_raises_runtime_error():
    """
    When both the primary model (3 attempts) and the fallback model fail,
    structured_completion should raise RuntimeError with a message that
    mentions both 'primary_error' and 'fallback_error'.

    acompletion call count should be 4 total: 3 primary attempts + 1 fallback.
    """
    client = LLMClient()

    # All 4 calls raise — primary and fallback both fail
    mock_call = AsyncMock(side_effect=RuntimeError("persistent api error"))

    with patch("litellm.acompletion", new=mock_call):
        with pytest.raises(RuntimeError, match="fallback_error"):
            await client.structured_completion(
                prompt="test prompt",
                schema=SimpleSchema,
                agent_name="test_agent",
            )

    # 3 primary attempts + 1 fallback attempt = 4 total calls
    assert mock_call.call_count == 4
