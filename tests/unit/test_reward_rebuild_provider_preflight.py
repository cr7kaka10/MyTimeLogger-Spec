import inspect

from server.server import _run_reward_rebuild


def test_reward_rebuild_validates_complete_read_only_provider_snapshot_before_reset():
    source = inspect.getsource(_run_reward_rebuild)
    preflight = source.index('stage = "provider_preflight"')
    validate_only = source.index("validate_only=True")
    completeness = source.index('not preflight.get("complete")')
    reset = source.index('stage = "ticktick_reset"')

    assert preflight < validate_only < completeness < reset
    assert 'not pull.get("complete")' in source
    assert 'provider_snapshot_stale' in source and 'provider_snapshot_changed' in source
    assert 'fail_and_restore' in source
