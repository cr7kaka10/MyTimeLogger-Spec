from server.provider_delta_filter import classify_provider_records


def test_lifecycle_precedes_identical_etag_without_using_historical_archive_time():
    local = {"h": {"status": 0, "source_etag": "same"}}
    archived = {"id": "h", "status": 1, "etag": "same"}
    assert classify_provider_records([archived], local, "habit").changed == [archived]
    active = {**archived, "status": 0, "archivedTime": "historical"}
    assert classify_provider_records([active], local, "habit").unchanged == [active]
    local["h"]["status"] = 1
    assert classify_provider_records([active], local, "habit").changed == [active]
    assert classify_provider_records([archived], local, "habit").unchanged == [archived]


def test_empty_records_never_produce_delete_facts():
    result = classify_provider_records([], {"h": {"status": 0}}, "habit")
    assert result.deleted_candidates == [] and result.records_to_upsert() == []
