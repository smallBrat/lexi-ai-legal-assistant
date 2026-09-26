"""Temporary script to verify Gemini API connectivity."""

import asyncio
import sys

from google import genai
from google.genai import types

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.core.config import get_gemini_key

MODEL_NAME = "gemini-2.5-flash"
PROMPT = "Summarize this sentence in JSON: The agreement terminates after 30 days."


async def main() -> None:
    client = genai.Client(api_key=get_gemini_key())
    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
    )
    try:
        response = await client.aio.models.generate_content(
            model=MODEL_NAME,
            contents=PROMPT,
            config=config,
        )
        print("=== Raw Gemini Response ===")
        print(response)
    except Exception as exc:
        print("=== SDK Exception ===")
        print(repr(exc))
        raise


if __name__ == "__main__":
    asyncio.run(main())
