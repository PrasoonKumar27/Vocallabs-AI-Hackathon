"""
End-to-end test for Part 05 (Orchestrator + FastAPI).

Tests:
1. Health endpoint
2. POST /api/task/start (returns task_id immediately)
3. WebSocket event streaming (connects, receives events, task completes)
4. Late-joiner event replay via GET /api/task/{task_id}/events
5. POST /api/chaos/set, then run a task with fault injection
6. Multiple runs in a single server process
"""

import asyncio
import json
import httpx
import websockets

BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"


async def test_health():
    print("=" * 60)
    print("TEST 1: Health endpoint")
    print("=" * 60)
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        print(f"  Health: {data}")
        assert data["status"] == "ok"
    print("  ✓ Health check passed\n")


async def test_happy_path():
    print("=" * 60)
    print("TEST 2: Happy path — full task end to end")
    print("=" * 60)

    # Start a task
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE}/api/task/start",
            json={"request": "Reschedule booking BKG123 to 2026-09-15"}
        )
        assert resp.status_code == 200
        data = resp.json()
        task_id = data["task_id"]
        print(f"  Task started: {task_id}")
        assert task_id.startswith("task_")

    # Connect WebSocket and collect events
    events = []
    try:
        async with websockets.connect(f"{WS_BASE}/ws/task/{task_id}") as ws:
            # Read events until task_completed or timeout
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    event = json.loads(msg)
                    events.append(event)
                    print(f"  [{event['event']}] {json.dumps({k:v for k,v in event.items() if k not in ('ts',)}, default=str)}")
                    if event["event"] == "task_completed":
                        break
                except asyncio.TimeoutError:
                    print("  ⚠ Timeout waiting for events")
                    break
    except Exception as e:
        print(f"  WS error: {e}")

    # Verify we got task_completed with success
    assert len(events) > 0, "No events received"
    last = events[-1]
    assert last["event"] == "task_completed", f"Last event should be task_completed, got {last['event']}"
    assert last.get("success") is True, f"Task should succeed on happy path, got {last}"
    print(f"\n  ✓ Happy path completed: success={last['success']}, degraded={last.get('degraded')}")
    print(f"  ✓ Total events received: {len(events)}\n")
    return task_id


async def test_late_joiner(task_id: str):
    print("=" * 60)
    print("TEST 3: Late joiner — GET event history")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE}/api/task/{task_id}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert len(data["events"]) > 0
        event_types = [e["event"] for e in data["events"]]
        print(f"  Events in history: {len(data['events'])}")
        print(f"  Event types: {event_types}")
        assert "task_completed" in event_types
    print("  ✓ Late joiner can fetch full event history\n")


async def test_with_chaos():
    print("=" * 60)
    print("TEST 4: Task with chaos — ERROR_500 on lookup_booking")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Inject fault before starting task
        resp = await client.post(
            f"{BASE}/api/chaos/set",
            json={"tool": "lookup_booking", "fault": "ERROR_500", "count": 1}
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        print("  ✓ Chaos set: ERROR_500 x1 on lookup_booking")

        # Start task
        resp = await client.post(
            f"{BASE}/api/task/start",
            json={"request": "Reschedule BKG456 to 2026-10-01"}
        )
        task_id = resp.json()["task_id"]
        print(f"  Task started: {task_id}")

    # Collect events via WebSocket
    events = []
    try:
        async with websockets.connect(f"{WS_BASE}/ws/task/{task_id}") as ws:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    event = json.loads(msg)
                    events.append(event)
                    etype = event["event"]
                    if etype in ("fault_detected", "strategy_chosen", "state_transition", "escalated"):
                        print(f"  🔥 [{etype}] {json.dumps({k:v for k,v in event.items() if k not in ('ts',)}, default=str)}")
                    if etype == "task_completed":
                        break
                except asyncio.TimeoutError:
                    print("  ⚠ Timeout")
                    break
    except Exception as e:
        print(f"  WS error: {e}")

    last = events[-1]
    assert last["event"] == "task_completed"
    # Task should still complete (retry recovers from single ERROR_500)
    fault_events = [e for e in events if e["event"] == "fault_detected"]
    strategy_events = [e for e in events if e["event"] == "strategy_chosen"]
    assert len(fault_events) > 0, "Should have detected the injected fault"
    assert len(strategy_events) > 0, "Should have chosen a strategy"
    print(f"\n  ✓ Task completed despite chaos: success={last.get('success')}")
    print(f"  ✓ Faults detected: {len(fault_events)}, Strategies chosen: {len(strategy_events)}\n")


async def test_repeated_runs():
    print("=" * 60)
    print("TEST 5: Multiple runs in same server process")
    print("=" * 60)

    for i in range(3):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BASE}/api/task/start",
                json={"request": f"Reschedule BKG123 to 2026-09-{20+i}"}
            )
            task_id = resp.json()["task_id"]

        events = []
        try:
            async with websockets.connect(f"{WS_BASE}/ws/task/{task_id}") as ws:
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                        event = json.loads(msg)
                        events.append(event)
                        if event["event"] == "task_completed":
                            break
                    except asyncio.TimeoutError:
                        break
        except Exception as e:
            print(f"  Run {i+1} WS error: {e}")

        last = events[-1] if events else {}
        success = last.get("success", False)
        print(f"  Run {i+1}: {task_id} → success={success}, events={len(events)}")
        assert last.get("event") == "task_completed"
        assert success is True

    print("  ✓ All 3 runs completed successfully without server restart\n")


async def test_state_endpoint():
    print("=" * 60)
    print("TEST 6: GET /api/state — aggregate tool states")
    print("=" * 60)
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE}/api/state")
        assert resp.status_code == 200
        data = resp.json()
        print(f"  Aggregate state: {data['aggregate_state']}")
        print(f"  Tool states: {[t['tool'] + '=' + t['state'] for t in data['tool_states']]}")
        assert len(data["tool_states"]) == 4
    print("  ✓ State endpoint works\n")


async def main():
    await test_health()
    task_id = await test_happy_path()
    await test_late_joiner(task_id)
    await test_with_chaos()
    await test_repeated_runs()
    await test_state_endpoint()

    print("=" * 60)
    print("🎉  ALL PART 05 TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
