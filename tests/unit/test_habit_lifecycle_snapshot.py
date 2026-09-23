import asyncio
import pytest
from server.habit_lifecycle_contract import HabitLifecycleContract, validate_habit_list
from server.habit_lifecycle_snapshot import missing_candidates, detail_decision
from server.habit_lifecycle_probe import probe_habits

ROW = dict(id='ticktick:1:p', user_id=1, source='ticktick', provider_id='p', provider_binding_id='b', provider_observed_round=1)
CONTRACT = HabitLifecycleContract('dida365.com', 1, True, True, 'isolated-fixture-only', True, True, True)
MISSING = dict(state='unresolved_missing', status_code=404)


def decide(contract=CONTRACT, **overrides):
    args = dict(user_id=1, binding_id='b', round_id=3, current=True, auth_healthy=True, previous_missing_round=2)
    args.update(overrides)
    return detail_decision(ROW, MISSING, contract, **args)[0]


def test_gate_requires_calibration_current_binding_and_two_independent_rounds():
    assert decide() == 'deleted'
    assert decide(HabitLifecycleContract('dida365.com')) == 'unresolved'
    assert decide(HabitLifecycleContract('dida365.com', 1, False, True, 'archived-404')) == 'unresolved'
    for key, value in [('current',False), ('auth_healthy',False), ('binding_id','new'), ('previous_missing_round',None), ('round_id',2)]:
        assert decide(**{key:value}) == 'unresolved'
    assert missing_candidates([ROW, {**ROW,'source':'local'}, {**ROW,'user_id':2}], set(), 1, 'b') == [ROW]
    assert CONTRACT.state({'status':0,'archivedTime':'old'}) == 'active'
    assert CONTRACT.state({'status':True}) == 'unknown'
    assert CONTRACT.state({'status':9}) == 'unknown'
    assert validate_habit_list([], CONTRACT) == ([], [])
    with pytest.raises(ValueError): validate_habit_list([], CONTRACT, pages_complete=False)
    with pytest.raises(ValueError): validate_habit_list([{'id':'p','status':0}]*2, CONTRACT)


def test_positive_detail_and_budget_preserve_missing_candidates():
    detail = dict(state='present', record={'id':'p','status':0})
    assert detail_decision(ROW, detail, CONTRACT, user_id=1, binding_id='b', round_id=3, current=True, auth_healthy=True)[0] == 'active'
    class Client:
        async def get_habit_detail(self, pid): return MISSING
    rows = [{**ROW,'provider_id':str(i)} for i in range(20)]
    results, _, stats = asyncio.run(probe_habits(Client(), rows, {}, budget=4))
    assert len(results) == stats['detail_requests'] == 4 and stats['deferred_candidates'] == 16
    assert decide(round_id=1) == 'unresolved'
