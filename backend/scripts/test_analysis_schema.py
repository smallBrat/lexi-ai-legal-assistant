"""Validate sanitized Gemini schema and test a live API call."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.analysis_schema import LegalAnalysis
from app.utils.schema_utils import build_gemini_schema, validate_gemini_schema


def count_pattern(schema: dict | list | str, pattern: str) -> int:
    """Recursively count occurrences of a key pattern in a schema."""
    count = 0
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == pattern:
                count += 1
            count += count_pattern(value, pattern)
    elif isinstance(schema, list):
        for item in schema:
            count += count_pattern(item, pattern)
    return count


def main() -> None:
    from app.core.config import get_gemini_key
    from google import genai
    from google.genai import types

    schema = build_gemini_schema(LegalAnalysis)
    schema_size = len(json.dumps(schema))
    ref_count = count_pattern(schema, "$ref")
    defs_count = count_pattern(schema, "$defs")
    addl_count = count_pattern(schema, "additionalProperties")

    print("=== Schema Validation ===")
    print(f"Schema size:                    {schema_size} bytes")
    print(f"Refs remaining:                 {ref_count}")
    print(f"Defs remaining:                 {defs_count}")
    print(f"additionalProperties remaining: {addl_count}")

    if ref_count or defs_count or addl_count:
        print("FAIL")
        sys.exit(1)

    try:
        validate_gemini_schema(schema)
        print("Schema valid ✓")
    except Exception as exc:
        print(f"FAIL - {exc}")
        sys.exit(1)

    print("\n=== Clause Schema ===")
    print(json.dumps(schema["properties"]["clauses"]["items"], indent=2))
    print("\nClause required fields:")
    print(schema["properties"]["clauses"]["items"]["required"])

    print()
    print("=== Live Gemini Call ===")
    client = genai.Client(api_key=get_gemini_key())
    config = types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=schema,
    )
    prompt = "Summarize this sentence in JSON: The agreement terminates after 30 days."

    async def run() -> None:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        text = getattr(response, "text", None)
        print(f"Raw response:\n{text}")
        parsed = json.loads(text)
        validated = LegalAnalysis.model_validate_json(json.dumps(parsed))
        print()
        print(f"risk_score:    {validated.risk_score}")
        print(f"risk_level:    {validated.risk_level}")
        print(f"summary:       {validated.summary[:80]}...")
        print(f"doc_type:      {validated.document_type}")
        print(f"read_diff:     {validated.reading_difficulty}")
        print()
        print("Live Gemini call ✓")
        print("Pydantic validation ✓")
        print()
        print("PASS")

    asyncio.run(run())


if __name__ == "__main__":
    main()
