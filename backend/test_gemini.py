import asyncio
import os
from dotenv import load_dotenv

load_dotenv("../.env")
import litellm
litellm._turn_on_debug()


async def test():
    api_key = os.getenv("LLM_API_KEY")
    print(f"Key prefix: {api_key[:8] if api_key else 'NOT SET'}...")
    try:
        resp = await litellm.acompletion(
            model="gemini/gemini-3.5-flash",
            messages=[{"role": "user", "content": "Reply with just the word: pong"}],
            api_key=api_key,
        )
        print("SUCCESS:", resp.choices[0].message.content)
    except Exception as e:
        print("FAILED:", e)


asyncio.run(test())
