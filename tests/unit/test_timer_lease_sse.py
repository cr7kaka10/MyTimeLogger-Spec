import asyncio
import json

from server.sync_hub import SyncHub


def test_timer_state_event_is_user_isolated_and_minimal():
    async def run():
        hub = SyncHub(None)
        own = asyncio.Queue()
        other = asyncio.Queue()
        anonymous = asyncio.Queue()
        hub.subscribe(own, 7)
        hub.subscribe(other, 8)
        hub.subscribe(anonymous)

        hub.notify_timer_state(7, 4)

        message = await asyncio.wait_for(own.get(), timeout=0.1)
        assert message["event"] == "timer-state-changed"
        assert json.loads(message["data"]) == {"revision": 4}
        assert other.empty()
        assert anonymous.empty()

    asyncio.run(run())


def test_changed_event_remains_compatible_for_unscoped_subscribers():
    async def run():
        hub = SyncHub(None)
        scoped = asyncio.Queue()
        unscoped = asyncio.Queue()
        hub.subscribe(scoped, 7)
        hub.subscribe(unscoped)

        hub._notify_clients(["tasks"], user_id=7)

        assert json.loads((await scoped.get())["data"]) == {"tables": ["tasks"]}
        assert json.loads((await unscoped.get())["data"]) == {"tables": ["tasks"]}

    asyncio.run(run())


def test_completed_session_event_is_user_isolated_and_uses_changed_contract():
    async def run():
        hub = SyncHub(None)
        own = asyncio.Queue()
        other = asyncio.Queue()
        anonymous = asyncio.Queue()
        hub.subscribe(own, 7)
        hub.subscribe(other, 8)
        hub.subscribe(anonymous)

        hub.notify_completed_session(7)

        message = await asyncio.wait_for(own.get(), timeout=0.1)
        assert message["event"] == "changed"
        assert json.loads(message["data"]) == {"tables": ["study_sessions"]}
        assert other.empty()
        assert anonymous.empty()

    asyncio.run(run())
