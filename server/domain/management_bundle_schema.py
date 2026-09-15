"""Bundle v1 图模型的模式定义与严格校验"""
import hashlib
import json
import re
from typing import Any


BUNDLE_SCHEMA_ID = "mytimelogger.management-bundle"
BUNDLE_VERSION = 1
MAX_BUNDLE_SIZE_BYTES = 20 * 1024 * 1024

LOGICAL_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,80}\.[a-z0-9][a-z0-9._-]{0,120}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

NODE_TYPES = {
    "category", "task", "habit", 
    "learning-objective", "learning-kr", "learning-task",
    "exercise-plan", "exercise-item", 
    "goal", "store-item"
}

RELATION_TYPES = {
    "child_of", "contains", "unlocks", "rewards", "binds"
}

STATUS_TYPES = {"active", "archived"}

BLACK_LISTED_FIELDS = {
    "user_id", "id", "token", "raw_json", "provider_id", "sql", "query", "table",
    "api_key", "password", "wallet", "wallet_balance", "backpack_events",
    "sync_queue", "calendar_event", "calendar_events", "hourly_schedule"
}


class BundleValidationError(ValueError):
    def __init__(self, code: str, message: str, *, path: str = ""):
        super().__init__(message)
        self.code = code
        self.path = path


def validate_bundle_size(raw_bytes: bytes) -> None:
    if len(raw_bytes) > MAX_BUNDLE_SIZE_BYTES:
        raise BundleValidationError("management_bundle_too_large", "Bundle size exceeds 20MB limit")
    try:
        raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        raise BundleValidationError("management_bundle_encoding", "Bundle must be valid UTF-8")


def _sort_dict(d: dict[str, Any]) -> dict[str, Any]:
    return {k: _sort_value(d[k]) for k in sorted(d.keys())}


def _sort_value(v: Any) -> Any:
    if isinstance(v, dict):
        return _sort_dict(v)
    elif isinstance(v, list):
        # Arrays might have semantic order, but for canonicalization of bundle nodes/relations,
        # we will sort them by their JSON string representation if they are objects.
        try:
            return sorted([_sort_value(x) for x in v], key=lambda x: json.dumps(x, separators=(',', ':'), sort_keys=True))
        except TypeError:
            return v
    return v


def canonicalize_bundle(bundle: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """生成完全确定的规范化 Bundle 和 Digest"""
    canon = {
        "schema": bundle.get("schema", BUNDLE_SCHEMA_ID),
        "version": bundle.get("version", BUNDLE_VERSION),
        "nodes": sorted([_sort_dict(n) for n in bundle.get("nodes", [])], key=lambda x: x.get("logical_key", "")),
        "relations": sorted([_sort_dict(r) for r in bundle.get("relations", [])], key=lambda x: f"{x.get('source_key')}:{x.get('target_key')}:{x.get('type')}"),
        "presentation": _sort_dict(bundle.get("presentation", {"groups": []})),
        "unresolved_relations": sorted([_sort_dict(r) for r in bundle.get("unresolved_relations", [])], key=lambda x: f"{x.get('source_key')}:{x.get('target_key')}")
    }
    digest = hashlib.sha256(json.dumps(canon, separators=(',', ':')).encode('utf-8')).hexdigest()
    return digest, canon


def validate_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("schema") != BUNDLE_SCHEMA_ID:
        raise BundleValidationError("management_bundle_schema_invalid", "Invalid schema")
    
    version = bundle.get("version")
    if version != BUNDLE_VERSION:
        raise BundleValidationError("management_bundle_version_unsupported", f"Unsupported version: {version}")

    nodes = bundle.get("nodes", [])
    if not isinstance(nodes, list):
        raise BundleValidationError("management_bundle_format", "Nodes must be a list", path="nodes")
    
    relations = bundle.get("relations", [])
    if not isinstance(relations, list):
        raise BundleValidationError("management_bundle_format", "Relations must be a list", path="relations")
    
    unresolved_relations = bundle.get("unresolved_relations", [])
    if not isinstance(unresolved_relations, list):
        raise BundleValidationError("management_bundle_format", "Unresolved relations must be a list", path="unresolved_relations")

    presentation = bundle.get("presentation", {})
    if not isinstance(presentation, dict):
        raise BundleValidationError("management_bundle_format", "Presentation must be an object", path="presentation")

    keys_seen = set()
    for idx, node in enumerate(nodes):
        path = f"nodes[{idx}]"
        if not isinstance(node, dict):
            raise BundleValidationError("management_bundle_format", "Node must be an object", path=path)
        
        logical_key = node.get("logical_key")
        if not isinstance(logical_key, str) or not LOGICAL_KEY_RE.match(logical_key):
            raise BundleValidationError("management_bundle_invalid_key", f"Invalid logical key: {logical_key}", path=path)
        
        if logical_key in keys_seen:
            raise BundleValidationError("management_bundle_duplicate_key", f"Duplicate logical key: {logical_key}", path=path)
        keys_seen.add(logical_key)

        node_type = node.get("type")
        if node_type not in NODE_TYPES:
            raise BundleValidationError("management_bundle_invalid_node_type", f"Invalid node type: {node_type}", path=path)

        status = node.get("status", "active")
        if status not in STATUS_TYPES:
            raise BundleValidationError("management_bundle_invalid_status", f"Invalid status: {status}", path=path)

        data = node.get("data", {})
        if not isinstance(data, dict):
            raise BundleValidationError("management_bundle_format", "Node data must be an object", path=path)

        for key in data:
            if key in BLACK_LISTED_FIELDS:
                raise BundleValidationError("management_bundle_forbidden_field", f"Forbidden field: {key}", path=f"{path}.data.{key}")
            if isinstance(data[key], str) and len(data[key]) > 10000:
                raise BundleValidationError("management_bundle_field_too_long", f"Field {key} exceeds length limit", path=f"{path}.data.{key}")
        
        _validate_node_data(node_type, data, path)

    _validate_relations(relations, keys_seen)


def _validate_node_data(node_type: str, data: dict[str, Any], path: str) -> None:
    if "color" in data and data["color"] and not COLOR_RE.match(str(data["color"])):
        raise BundleValidationError("management_bundle_invalid_color", "Invalid color format", path=f"{path}.data.color")
    
    if node_type in ("category", "task", "habit"):
        pass  # 基础属性，依赖外层的基础长度校验即可
    elif node_type == "learning-objective":
        if "target_description" in data and not isinstance(data["target_description"], str):
            raise BundleValidationError("management_bundle_invalid_type", "target_description must be string", path=f"{path}.data.target_description")
    elif node_type == "learning-kr":
        if "target_value" in data and not isinstance(data["target_value"], (int, float)):
            raise BundleValidationError("management_bundle_invalid_type", "target_value must be number", path=f"{path}.data.target_value")
    elif node_type == "learning-task":
        if "due_date" in data and data["due_date"] and not DATE_RE.match(str(data["due_date"])):
            raise BundleValidationError("management_bundle_invalid_date", "Invalid due date", path=f"{path}.data.due_date")
    elif node_type == "exercise-plan":
        pass
    elif node_type == "exercise-item":
        if "sets" in data and not isinstance(data["sets"], str):
            raise BundleValidationError("management_bundle_invalid_type", "sets must be string", path=f"{path}.data.sets")
    elif node_type == "goal":
        if "metric" in data and not isinstance(data["metric"], str):
            raise BundleValidationError("management_bundle_invalid_type", "metric must be string", path=f"{path}.data.metric")
    elif node_type == "store-item":
        if "price" in data and not isinstance(data["price"], (int, float)):
            raise BundleValidationError("management_bundle_invalid_type", "price must be number", path=f"{path}.data.price")


def _validate_relations(relations: list[dict[str, Any]], keys_seen: set[str]) -> None:
    # 建立父子索引，以检测循环和层级合法性
    parent_map = {}
    
    for idx, rel in enumerate(relations):
        path = f"relations[{idx}]"
        if not isinstance(rel, dict):
            raise BundleValidationError("management_bundle_format", "Relation must be an object", path=path)
        
        rel_type = rel.get("type")
        if rel_type not in RELATION_TYPES:
            raise BundleValidationError("management_bundle_invalid_relation_type", f"Invalid relation type: {rel_type}", path=path)
        
        src = rel.get("source_key")
        tgt = rel.get("target_key")
        if src not in keys_seen:
            raise BundleValidationError("management_bundle_dangling_reference", f"Dangling reference: {src}", path=path)
        if tgt not in keys_seen:
            raise BundleValidationError("management_bundle_dangling_reference", f"Dangling reference: {tgt}", path=path)
            
        if rel_type == "child_of":
            parent_map[src] = tgt

            # Type checking for child_of
            src_type = src.split(".")[0]
            tgt_type = tgt.split(".")[0]
            
            valid_parents = {
                "learning-kr": {"learning-objective"},
                "learning-task": {"learning-kr"},
                "exercise-item": {"exercise-plan"},
                "learning-objective": {"category"},
                "exercise-plan": {"category"},
                "task": {"category"},
                "habit": {"category"},
                "goal": {"category"},
                "category": {"category"}
            }
            if src_type in valid_parents:
                if tgt_type not in valid_parents[src_type]:
                    raise BundleValidationError("management_bundle_invalid_hierarchy", f"{src_type} cannot be child of {tgt_type}", path=path)
            elif src_type == "store-item":
                raise BundleValidationError("management_bundle_invalid_hierarchy", "store-item cannot be a child", path=path)

    # 循环检测
    for node in keys_seen:
        visited = set()
        current = node
        while current in parent_map:
            visited.add(current)
            current = parent_map[current]
            if current in visited:
                raise BundleValidationError("management_bundle_cycle_detected", f"Cycle detected involving {current}", path="relations")
