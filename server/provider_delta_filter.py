# -*- coding: utf-8 -*-
"""Fast provider-side delta classification for TickTick pull records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


class MissingProviderFingerprintError(ValueError):
    """Raised when TickTick omits the fingerprint required for safe incremental sync."""

    def __init__(self, record_type: str, record_key: str, field_name: str):
        self.record_type = record_type
        self.record_key = record_key
        self.field_name = field_name
        super().__init__(
            f"TickTick {record_type} record {record_key or '<missing-key>'} missing required {field_name}"
        )


@dataclass
class ProviderDeltaResult:
    new: list[dict[str, Any]] = field(default_factory=list)
    changed: list[dict[str, Any]] = field(default_factory=list)
    unchanged: list[dict[str, Any]] = field(default_factory=list)
    deleted_candidates: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.new) + len(self.changed) + len(self.unchanged)

    def records_to_upsert(self) -> list[dict[str, Any]]:
        return [*self.new, *self.changed]

    def stats(self) -> dict[str, int]:
        return {
            "total": self.total,
            "new": len(self.new),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
            "deleted_candidates": len(self.deleted_candidates),
        }


def provider_key(record: Mapping[str, Any]) -> str:
    return str(record.get("_provider_key") or record.get("id") or record.get("ticktick_id") or "")


def provider_fingerprint(record: Mapping[str, Any], record_type: str) -> str:
    if record_type in {"task", "habit"}:
        return str(record.get("etag") or record.get("source_etag") or "")
    if record_type == "habit_checkin":
        return str(record.get("opTime") or record.get("source_modified_time") or "")
    raise ValueError(f"Unsupported provider record type: {record_type}")


def required_fingerprint_field(record_type: str) -> str:
    if record_type in {"task", "habit"}:
        return "etag"
    if record_type == "habit_checkin":
        return "opTime"
    raise ValueError(f"Unsupported provider record type: {record_type}")


def local_fingerprint(row: Mapping[str, Any] | None, record_type: str) -> str:
    if not row:
        return ""
    if record_type in {"task", "habit"}:
        return str(row.get("source_etag") or row.get("etag") or "")
    if record_type == "habit_checkin":
        return str(row.get("source_modified_time") or row.get("opTime") or "")
    raise ValueError(f"Unsupported provider record type: {record_type}")


def classify_provider_records(
    records: Sequence[Mapping[str, Any]],
    local_fingerprints: Mapping[str, Mapping[str, Any]],
    record_type: str,
    *,
    include_deleted_candidates: bool = False,
) -> ProviderDeltaResult:
    """Classify provider records using only etag for tasks/habits and opTime for checkins."""

    result = ProviderDeltaResult()
    seen_keys: set[str] = set()
    for raw in records:
        record = dict(raw)
        key = provider_key(record)
        if not key:
            raise MissingProviderFingerprintError(record_type, key, "id")
        seen_keys.add(key)
        remote_fp = provider_fingerprint(record, record_type)
        if not remote_fp:
            raise MissingProviderFingerprintError(record_type, key, required_fingerprint_field(record_type))
        local_row = local_fingerprints.get(key)
        if not local_row:
            result.new.append(record)
            continue
        if record_type == "task" and local_row.get("deleted_at"):
            result.changed.append(record)
            continue
        if remote_fp == local_fingerprint(local_row, record_type):
            result.unchanged.append(record)
        else:
            result.changed.append(record)

    if include_deleted_candidates:
        result.deleted_candidates = sorted(set(local_fingerprints.keys()) - seen_keys)
    return result
