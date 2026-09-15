"""最小中文校对的确定性结果守卫。"""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher


_LITERAL = re.compile(r"[a-z][a-z0-9._+-]*|\d+(?:\.\d+)*", re.I)
_OBVIOUS_REPLACEMENTS = (("今夭", "今天"), ("烦烦", "烦"))
_REDUNDANT_APPROXIMATION = re.compile(r"大约([^，。！？；、\s]{1,12})左右")


def _apply_obvious_corrections(text: str) -> str:
    """只处理无需语境推断的固定错字与重复字，不改写语气。"""
    corrected = text
    for source, replacement in _OBVIOUS_REPLACEMENTS:
        corrected = corrected.replace(source, replacement)
    return _REDUNDANT_APPROXIMATION.sub(r"大约\1", corrected)


def polish_edits(original: str, proposed: str) -> list[dict[str, str]]:
    """Return stable character-level edit evidence without retaining it in logs."""
    return [
        {"source": original[i1:i2], "replacement": proposed[j1:j2], "kind": tag}
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, original, proposed).get_opcodes()
        if tag != "equal"
    ]


def validate_minimal_polish(original: str, proposed: str) -> tuple[str, str, list[dict[str, str]]]:
    source, candidate = str(original or "").strip(), str(proposed or "").strip()
    if not candidate:
        return source, "polish_empty", []
    candidate = _apply_obvious_corrections(candidate)
    edits = polish_edits(source, candidate)
    if _LITERAL.findall(source) != _LITERAL.findall(candidate):
        return source, "polish_protected_literal", edits
    changed = sum(max(len(edit["source"]), len(edit["replacement"])) for edit in edits)
    budget = max(2, math.ceil(len(source) * 0.2))
    if source and changed > budget:
        return source, "polish_edit_budget", edits
    return candidate, "polish_accepted", edits
