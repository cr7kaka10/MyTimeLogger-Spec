import json
import pytest
from server.domain.management_bundle_schema import (
    validate_bundle_size, validate_bundle, canonicalize_bundle, BundleValidationError,
    BUNDLE_SCHEMA_ID, BUNDLE_VERSION
)

def test_bundle_size_and_encoding():
    with pytest.raises(BundleValidationError, match="limit"):
        validate_bundle_size(b"x" * (20 * 1024 * 1024 + 1))
    
    with pytest.raises(BundleValidationError, match="UTF-8"):
        validate_bundle_size(b"\xff\xfe")
        
    validate_bundle_size(b'{"schema": "mytimelogger.management-bundle"}')


def test_valid_bundle_canonicalization():
    bundle = {
        "version": 1,
        "nodes": [
            {"logical_key": "task.b", "type": "task", "status": "active", "data": {"title": "B"}},
            {"logical_key": "category.a", "type": "category", "status": "active", "data": {"title": "A"}}
        ],
        "relations": [
            {"source_key": "task.b", "target_key": "category.a", "type": "child_of"}
        ]
    }
    digest, canon = canonicalize_bundle(bundle)
    assert canon["schema"] == BUNDLE_SCHEMA_ID
    assert canon["version"] == 1
    # Check stable sort
    assert canon["nodes"][0]["logical_key"] == "category.a"
    assert canon["nodes"][1]["logical_key"] == "task.b"
    
    # Check that another dict with different order produces same digest
    bundle_alt = {
        "nodes": [
            {"type": "category", "status": "active", "logical_key": "category.a", "data": {"title": "A"}},
            {"type": "task", "status": "active", "data": {"title": "B"}, "logical_key": "task.b"}
        ],
        "relations": [
            {"type": "child_of", "target_key": "category.a", "source_key": "task.b"}
        ]
    }
    digest_alt, _ = canonicalize_bundle(bundle_alt)
    assert digest == digest_alt


def test_invalid_schema_and_version():
    with pytest.raises(BundleValidationError, match="Invalid schema"):
        validate_bundle({"schema": "wrong"})
        
    with pytest.raises(BundleValidationError, match="Unsupported version"):
        validate_bundle({"schema": BUNDLE_SCHEMA_ID, "version": 2})


def test_invalid_node_properties():
    bundle = {
        "schema": BUNDLE_SCHEMA_ID,
        "version": 1,
        "nodes": [
            {"logical_key": "task.1", "type": "unknown", "data": {}}
        ]
    }
    with pytest.raises(BundleValidationError, match="Invalid node type"):
        validate_bundle(bundle)

    bundle["nodes"][0]["type"] = "task"
    bundle["nodes"][0]["status"] = "deleted"
    with pytest.raises(BundleValidationError, match="Invalid status"):
        validate_bundle(bundle)

    bundle["nodes"][0]["status"] = "active"
    bundle["nodes"][0]["logical_key"] = "invalid key!!!"
    with pytest.raises(BundleValidationError, match="Invalid logical key"):
        validate_bundle(bundle)

    bundle["nodes"][0]["logical_key"] = "task.1"
    bundle["nodes"][0]["data"] = {"user_id": 123}
    with pytest.raises(BundleValidationError, match="Forbidden field"):
        validate_bundle(bundle)


def test_hierarchy_validation():
    bundle = {
        "schema": BUNDLE_SCHEMA_ID,
        "version": 1,
        "nodes": [
            {"logical_key": "learning-kr.1", "type": "learning-kr", "data": {}},
            {"logical_key": "learning-objective.1", "type": "learning-objective", "data": {}}
        ],
        "relations": [
            {"source_key": "learning-kr.1", "target_key": "learning-objective.1", "type": "child_of"}
        ]
    }
    validate_bundle(bundle)  # Should pass

    # Test invalid hierarchy
    bundle["relations"][0]["source_key"] = "learning-objective.1"
    bundle["relations"][0]["target_key"] = "learning-kr.1"
    with pytest.raises(BundleValidationError, match="cannot be child of"):
        validate_bundle(bundle)


def test_cycle_detection():
    bundle = {
        "schema": BUNDLE_SCHEMA_ID,
        "version": 1,
        "nodes": [
            {"logical_key": "category.1", "type": "category", "data": {}},
            {"logical_key": "category.2", "type": "category", "data": {}},
            {"logical_key": "category.3", "type": "category", "data": {}}
        ],
        "relations": [
            {"source_key": "category.1", "target_key": "category.2", "type": "child_of"},
            {"source_key": "category.2", "target_key": "category.3", "type": "child_of"},
            {"source_key": "category.3", "target_key": "category.1", "type": "child_of"}
        ]
    }
    with pytest.raises(BundleValidationError, match="Cycle detected"):
        validate_bundle(bundle)


def test_dangling_reference():
    bundle = {
        "schema": BUNDLE_SCHEMA_ID,
        "version": 1,
        "nodes": [
            {"logical_key": "task.1", "type": "task", "data": {}}
        ],
        "relations": [
            {"source_key": "task.1", "target_key": "category.missing", "type": "child_of"}
        ]
    }
    with pytest.raises(BundleValidationError, match="Dangling reference: category.missing"):
        validate_bundle(bundle)
