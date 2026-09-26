"""Input sanitization utilities (Phase 15 hardening).

Centralizes text sanitization for user-controlled free-text fields
(titles, search queries). Strips ANSI escape sequences and C0/C1 control
characters (log-forging and terminal-injection vectors) while preserving
normal Unicode. Length limits stay in the Pydantic schemas; this module
handles character-class hygiene.
"""

import re

# C0 controls (0x00-0x1F) except tab/newline handled separately, DEL (0x7F),
# C1 controls (0x80-0x9F), and ANSI CSI/OSC escape sequences.
_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")


def sanitize_text(value: str | None, max_length: int = 500) -> str:
    """Sanitize a free-text field.

    Removes ANSI escape sequences and control characters, collapses
    whitespace runs, and clamps to ``max_length``. Returns an empty
    string for ``None``/non-string input.
    """
    if not value or not isinstance(value, str):
        return ""
    cleaned = _ANSI_RE.sub("", value)
    cleaned = _CONTROL_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned[:max_length]
