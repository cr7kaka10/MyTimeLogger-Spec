# -*- coding: utf-8 -*-
"""Allow-list for SQL identifiers used by multi-device sync."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SyncTableSpec:
    client_table: str
    server_table: str
    primary_key: str = "id"
    ownership: str = "client_writable"
    direction: str = "bidirectional"
    outbox: bool = True


_REGISTRY = json.loads(
    (Path(__file__).parents[1] / "shared" / "protocol" / "sync-entities.json").read_text(encoding="utf-8")
)
_SPECS = [
    SyncTableSpec(
        entity["clientTable"], entity["serverTable"], entity["primaryKey"],
        entity.get("ownership", "client_writable"), entity.get("direction", "bidirectional"),
        bool(entity.get("outbox", True)),
    )
    for entity in _REGISTRY["entities"]
]

SYNC_TABLE_SPECS = {spec.client_table: spec for spec in _SPECS}
SYNC_TABLES = tuple(SYNC_TABLE_SPECS.keys())
SYNC_TABLE_SET = set(SYNC_TABLES)
SERVER_TO_CLIENT_TABLE = {spec.server_table: spec.client_table for spec in _SPECS}
SERVER_TABLES = tuple(spec.server_table for spec in _SPECS)


def sync_table_spec(client_table: str) -> SyncTableSpec:
    try:
        return SYNC_TABLE_SPECS[client_table]
    except KeyError as exc:
        raise ValueError(f"Unsupported sync table: {client_table}") from exc


def server_table_for(client_table: str) -> str:
    return sync_table_spec(client_table).server_table


def primary_key_for(client_table: str) -> str:
    return sync_table_spec(client_table).primary_key


def is_server_owned(client_table: str) -> bool:
    spec = sync_table_spec(client_table)
    return spec.ownership == "server_owned" or spec.direction == "pull_only"


def client_table_for_server(server_table: str) -> str:
    try:
        return SERVER_TO_CLIENT_TABLE[server_table]
    except KeyError as exc:
        raise ValueError(f"Unsupported server sync table: {server_table}") from exc


def ensure_server_table(server_table: str) -> str:
    if server_table not in SERVER_TO_CLIENT_TABLE:
        raise ValueError(f"Unsupported server sync table: {server_table}")
    return server_table
