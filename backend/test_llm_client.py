import asyncio
from dotenv import load_dotenv

load_dotenv("../.env")

from pydantic import BaseModel
from app.core.llm import LLMClient


class SentimentResult(BaseModel):
    sentiment: str        # "positive", "negative", or "neutral"
    confidence: float     # 0.0 – 1.0
    reason: str


async def test():
    client = LLMClient()
    print(f"Provider : {client._provider}")
    print(f"Model    : {client._model}")
    print(f"Key prefix: {client._api_key[:8] if client._api_key else 'NOT SET'}...")
    print()

    prompt = (
        "Analyse the sentiment of this text and return JSON.\n\n"
        "Text: 'The product works great and the support team was very helpful!'\n\n"
        "Return JSON with fields: sentiment (positive/negative/neutral), "
        "confidence (float 0-1), reason (one sentence)."
    )

    print("Calling structured_completion ...")
    result: SentimentResult = await client.structured_completion(
        prompt=prompt,
        schema=SentimentResult,
        agent_name="test_agent",
    )

    print("SUCCESS")
    print(f"  sentiment  : {result.sentiment}")
    print(f"  confidence : {result.confidence}")
    print(f"  reason     : {result.reason}")
    assert result.sentiment in ("positive", "negative", "neutral"), "Bad sentiment value"
    assert 0.0 <= result.confidence <= 1.0, "Confidence out of range"
    assert isinstance(result.reason, str) and result.reason, "Empty reason"
    print()
    print("All assertions passed.")


asyncio.run(test())
