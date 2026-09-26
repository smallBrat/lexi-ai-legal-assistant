"""Gemini-compatible JSON Schema builder from Pydantic models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_GEMINI_UNSUPPORTED_TOP_LEVEL = frozenset({
    "additionalProperties",
    "additional_properties",
    "title",
    "default",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "$defs",
    "definitions",
    "format",
    "nullable",
    "anyOf",
    "allOf",
    "oneOf",
})


class GeminiSchemaError(Exception):
    """Raised when a schema violates Gemini constraints."""


def _inline_refs(
    schema: dict[str, Any],
    defs: dict[str, Any],
    in_properties: bool = False,
) -> dict[str, Any]:
    """Recursively inline $ref while preserving property names like 'title'."""

    if "$ref" in schema:
        ref_key = schema["$ref"].rsplit("/", 1)[-1]
        resolved = dict(defs[ref_key])
        return _inline_refs(resolved, defs, in_properties)

    cleaned: dict[str, Any] = {}

    for key, value in schema.items():

        # IMPORTANT:
        # Skip Gemini-unsupported schema keywords only when they are schema keywords,
        # NOT when they are property names inside "properties".
        if not in_properties and key in _GEMINI_UNSUPPORTED_TOP_LEVEL:
            continue

        if key == "properties":
            cleaned["properties"] = {
                prop_name: _inline_refs(prop_schema, defs, in_properties=True)
                for prop_name, prop_schema in value.items()
            }
            continue

        if isinstance(value, dict):
            cleaned[key] = _inline_refs(value, defs)
        elif isinstance(value, list):
            cleaned[key] = [
                _inline_refs(item, defs) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value

    return cleaned


def _sanitize(schema: dict[str, Any], in_properties: bool = False) -> dict[str, Any]:
    """Post-process: strip unsupported keys, fix ``required`` lists."""
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "properties" and not in_properties:
            sanitized_props: dict[str, Any] = {}
            for prop_name, prop_schema in value.items():
                if isinstance(prop_schema, dict):
                    sanitized_props[prop_name] = _sanitize(prop_schema, in_properties=True)
                else:
                    sanitized_props[prop_name] = prop_schema
            cleaned["properties"] = sanitized_props
            continue
        if key in _GEMINI_UNSUPPORTED_TOP_LEVEL and not in_properties:
            continue
        if isinstance(value, dict):
            cleaned[key] = _sanitize(value, in_properties=(key == "properties"))
        elif isinstance(value, list):
            cleaned[key] = [
                _sanitize(item, in_properties=in_properties) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value

    if "required" in cleaned and "properties" in cleaned:
        prop_keys = set(cleaned["properties"].keys())
        cleaned["required"] = [r for r in cleaned["required"] if r in prop_keys]
        if not cleaned["required"]:
            del cleaned["required"]

    return cleaned


def _validate_recursive(schema: dict[str, Any], path: str = "$") -> None:
    """Recursively verify Gemini schema constraints."""
    if "required" in schema and "properties" in schema:
        prop_keys = set(schema["properties"].keys())
        for r in schema["required"]:
            if r not in prop_keys:
                raise GeminiSchemaError(
                    f"Orphan required '{r}' at {path} (not in properties)"
                )

    for key, value in schema.items():
        if isinstance(value, dict):
            _validate_recursive(value, f"{path}.{key}")
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    _validate_recursive(item, f"{path}.{key}[{idx}]")


def build_gemini_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Build a fully inlined, Gemini-compatible JSON schema for ANY model.

    Same inline + sanitize + validate pipeline as ``build_gemini_schema``
    but without the analysis-specific clause assertions, so chat (and
    future compare) payloads get the identical treatment that makes the
    analysis schema accepted by the Gemini API (no ``$ref``/``$defs``,
    no unsupported keywords — those are rejected with 400 InvalidArgument).
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})
    schema = _inline_refs(raw, defs)
    schema = _sanitize(schema)
    _validate_recursive(schema)
    return schema


def build_gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Build a fully inlined, Gemini-compatible JSON schema from a Pydantic model.

    - Inlines every ``$ref``.
    - Removes all unsupported keys.
    - Recalculates ``required`` so ``required ⊆ properties.keys()``.
    - Validates the result before returning.
    """
    schema = build_gemini_schema_for(model)

    clause_props = schema.get("properties", {}).get("clauses", {}).get("items", {}).get("properties", {})
    clause_required = schema.get("properties", {}).get("clauses", {}).get("items", {}).get("required", [])
    if "title" not in clause_props:
        raise GeminiSchemaError("Missing 'title' property in clause schema")
    if "title" not in clause_required:
        raise GeminiSchemaError("Missing 'title' in clause required fields")

    return schema


def validate_gemini_schema(schema: dict[str, Any]) -> None:
    """Raise ``GeminiSchemaError`` if the schema violates Gemini constraints."""
    _validate_recursive(schema)
    for key in _GEMINI_UNSUPPORTED_TOP_LEVEL:
        if key in schema:
            raise GeminiSchemaError(f"Unsupported top-level key: {key}")
