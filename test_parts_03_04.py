"""
Tests for Part 04 (Model Router) and Part 03 (Resilience Core).

Runs WITHOUT real API keys — exercises the rule-based fallback path,
the failover event emission, FORCE_PRIMARY_DOWN, and the full resilience
state machine with chaos-injected tool calls.
"""

import asyncio
import os
import sys
import time

# Ensure no API keys so we hit the rule-based fallback
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

from backend.model_router import plan_next_action, decide_strategy, set_failover_callback
from backend.chaos_middleware import chaos_config, ChaosSetRequest, set_chaos
from backend.resilience_core import (
    execute_tool_call,
    get_tool_state,
    get_all_states,
    get_aggregate_state,
    reset_all_states,
    set_event_callback,
    EscalationError,
)
from backend.tools.booking_api import lookup_booking
from backend.tools.availability_api import check_availability
from backend.tools.payment_api import charge_fare_difference
from backend.tools.notification_api import send_confirmation

# ---------------------------------------------------------------------------
# Event collectors for assertions
# ---------------------------------------------------------------------------
events: list[dict] = []
failover_events: list[dict] = []


async def collect_event(event: dict):
    events.append(event)


async def collect_failover(event: dict):
    failover_events.append(event)


set_event_callback(collect_event)
set_failover_callback(collect_failover)


# ---------------------------------------------------------------------------
# Part 04 tests
# ---------------------------------------------------------------------------
async def test_plan_next_action():
    print("=" * 60)
    print("PART 04 — Model Router Tests")
    print("=" * 60)

    # Test 1: Plan from empty state → should pick lookup_booking
    print("\n[04-1] plan_next_action — empty state")
    result = await plan_next_action({
        "request": "Reschedule BKG123 to 2026-09-15",
        "booking_id": "BKG123",
        "new_date": "2026-09-15",
        "results": {},
    })
    print(f"  Result: {result}")
    assert result["tool"] == "lookup_booking", f"Expected lookup_booking, got {result['tool']}"
    assert "model_used" in result
    assert "args" in result
    print("  ✓ Correct tool selected")

    # Test 2: Plan with lookup done → should pick check_availability
    print("\n[04-2] plan_next_action — after lookup")
    result = await plan_next_action({
        "request": "Reschedule BKG123 to 2026-09-15",
        "booking_id": "BKG123",
        "new_date": "2026-09-15",
        "results": {
            "lookup_booking": {"booking_id": "BKG123", "passenger_name": "Alice", "route": "DEL-BOM", "date": "2026-09-01", "fare": 150.0}
        },
    })
    print(f"  Result: {result}")
    assert result["tool"] == "check_availability"
    print("  ✓ Correct tool selected")

    # Test 3: Decide strategy for ERROR_500
    print("\n[04-3] decide_strategy — ERROR_500 attempt 1")
    result = await decide_strategy({
        "tool": "lookup_booking",
        "fault_type": "ERROR_500",
        "attempt": 1,
        "task_stakes": "normal",
    })
    print(f"  Result: {result}")
    assert result["strategy"] in {"RETRY_IMMEDIATE", "RETRY_BACKOFF", "SWITCH_MODEL", "USE_STALE_CACHE", "ESCALATE_TO_HUMAN"}
    assert "reasoning" in result and len(result["reasoning"]) > 3
    assert "model_used" in result
    print(f"  ✓ Strategy: {result['strategy']}, Reasoning: {result['reasoning']}")

    # Test 4: Decide strategy for high-stakes repeated failure → should escalate
    print("\n[04-4] decide_strategy — high stakes, attempt 3")
    result = await decide_strategy({
        "tool": "charge_fare_difference",
        "fault_type": "ERROR_500",
        "attempt": 3,
        "task_stakes": "high",
    })
    print(f"  Result: {result}")
    assert result["strategy"] == "ESCALATE_TO_HUMAN"
    print(f"  ✓ Correctly escalated: {result['reasoning']}")

    # Test 5: RATE_LIMIT → should backoff
    print("\n[04-5] decide_strategy — RATE_LIMIT")
    result = await decide_strategy({
        "tool": "send_confirmation",
        "fault_type": "RATE_LIMIT",
        "attempt": 1,
        "task_stakes": "normal",
    })
    print(f"  Result: {result}")
    assert result["strategy"] == "RETRY_BACKOFF"
    assert result["backoff_seconds"] is not None and result["backoff_seconds"] > 0
    print(f"  ✓ Backoff {result['backoff_seconds']}s")

    # Test 6: FORCE_PRIMARY_DOWN
    print("\n[04-6] FORCE_PRIMARY_DOWN failover event")
    failover_events.clear()
    os.environ["FORCE_PRIMARY_DOWN"] = "true"
    result = await plan_next_action({"request": "test", "results": {}, "booking_id": "BKG123", "new_date": "2026-09-15"})
    print(f"  Result: {result}")
    assert len(failover_events) > 0, "No failover event emitted"
    assert failover_events[-1]["reason"] == "forced_for_demo"
    print(f"  ✓ Failover event: {failover_events[-1]}")
    os.environ.pop("FORCE_PRIMARY_DOWN", None)

    print("\n✅ All Part 04 tests passed!")


# ---------------------------------------------------------------------------
# Part 03 tests
# ---------------------------------------------------------------------------
async def test_resilience_core():
    print("\n" + "=" * 60)
    print("PART 03 — Resilience Core Tests")
    print("=" * 60)

    reset_all_states()
    events.clear()

    # Test 1: Clean tool call (no chaos)
    print("\n[03-1] Clean lookup_booking call")
    t0 = time.time()
    result = await execute_tool_call("lookup_booking", lookup_booking, "BKG123")
    t1 = time.time()
    print(f"  Result: {result}, Time: {t1 - t0:.2f}s")
    assert result["booking_id"] == "BKG123"
    state = get_tool_state("lookup_booking")
    assert state["state"] == "HEALTHY"
    print(f"  ✓ State: {state['state']}")

    # Test 2: ERROR_500 with retry → should recover
    print("\n[03-2] ERROR_500 x1 then recover")
    reset_all_states()
    events.clear()
    await set_chaos(ChaosSetRequest(tool="lookup_booking", fault="ERROR_500", count=1))
    result = await execute_tool_call("lookup_booking", lookup_booking, "BKG123")
    print(f"  Result: {result}")
    assert result["booking_id"] == "BKG123"
    state = get_tool_state("lookup_booking")
    print(f"  ✓ Recovered to state: {state['state']}")
    # Check we got fault_detected and strategy_chosen events
    event_types = [e["event"] for e in events]
    assert "fault_detected" in event_types, f"Missing fault_detected, got: {event_types}"
    assert "strategy_chosen" in event_types, f"Missing strategy_chosen, got: {event_types}"
    print(f"  ✓ Events emitted: {event_types}")

    # Test 3: SILENT_NULL detection
    print("\n[03-3] SILENT_NULL detection and recovery")
    reset_all_states()
    events.clear()
    await set_chaos(ChaosSetRequest(tool="check_availability", fault="SILENT_NULL", count=1))
    result = await execute_tool_call("check_availability", check_availability, "2026-09-15", "DEL-BOM")
    print(f"  Result: {result}")
    assert result.get("available") is not None, "Should have recovered from SILENT_NULL"
    fault_events = [e for e in events if e["event"] == "fault_detected"]
    assert len(fault_events) > 0
    assert fault_events[0]["fault_type"] == "SILENT_NULL"
    print("  ✓ SILENT_NULL detected and recovered via retry")

    # Test 4: CORRUPT_PAYLOAD detection
    print("\n[03-4] CORRUPT_PAYLOAD detection and recovery")
    reset_all_states()
    events.clear()
    await set_chaos(ChaosSetRequest(tool="charge_fare_difference", fault="CORRUPT_PAYLOAD", count=1))
    result = await execute_tool_call("charge_fare_difference", charge_fare_difference, 50.0, "tok_123")
    print(f"  Result: {result}")
    assert result.get("charged") is True
    fault_events = [e for e in events if e["event"] == "fault_detected"]
    assert len(fault_events) > 0
    assert fault_events[0]["fault_type"] == "CORRUPT_PAYLOAD"
    print("  ✓ CORRUPT_PAYLOAD detected and recovered via retry")

    # Test 5: PAYMENT SAFETY NET — 2nd consecutive charge_fare_difference failure
    # forces ESCALATE regardless of model decision
    print("\n[03-5] Payment safety net — forced escalation on 2nd failure")
    reset_all_states()
    events.clear()
    # Set enough faults to trigger 2 consecutive failures
    await set_chaos(ChaosSetRequest(tool="charge_fare_difference", fault="ERROR_500", count=10))
    try:
        await execute_tool_call("charge_fare_difference", charge_fare_difference, 50.0, "tok_123")
        assert False, "Should have raised EscalationError"
    except EscalationError as e:
        print(f"  Caught: {e}")
        assert "payment safety net" in e.reasoning.lower() or "safety net" in e.reasoning.lower(), \
            f"Expected payment safety net reasoning, got: {e.reasoning}"
        state = get_tool_state("charge_fare_difference")
        assert state["state"] == "ESCALATED"
        assert state["consecutive_failures"] == 2, \
            f"Expected 2 consecutive failures (safety net triggers at 2), got {state['consecutive_failures']}"
        # Check that strategy_chosen event shows safety_net as model
        safety_events = [e for e in events if e.get("event") == "strategy_chosen" and e.get("model") == "safety_net"]
        assert len(safety_events) > 0, "Missing safety_net strategy event"
        print(f"  ✓ Payment safety net triggered at exactly 2 failures")
        print(f"  ✓ Strategy event model='safety_net': {safety_events[0]['reasoning']}")

    # Test 6: Repeated failures on NON-payment tool → goes through model decision
    # (should NOT trigger payment safety net, should exhaust retries instead)
    print("\n[03-6] Non-payment repeated failures → exhausts retries normally")
    reset_all_states()
    events.clear()
    await set_chaos(ChaosSetRequest(tool="send_confirmation", fault="ERROR_500", count=10))
    try:
        await execute_tool_call(
            "send_confirmation", send_confirmation,
            "user@test.com", {"booking_id": "BKG123", "route": "DEL-BOM"}
        )
        assert False, "Should have raised EscalationError"
    except EscalationError:
        pass
    state = get_tool_state("send_confirmation")
    assert state["state"] == "ESCALATED"
    # No safety_net events for non-payment tools
    safety_events = [e for e in events if e.get("event") == "strategy_chosen" and e.get("model") == "safety_net"]
    assert len(safety_events) == 0, "Safety net should NOT trigger for non-payment tools"
    print(f"  ✓ Non-payment tool escalated normally (no safety net)")

    # Test 7: State transitions (HEALTHY → DEGRADED → CIRCUIT_OPEN) with N=3
    print("\n[03-7] State transition chain with N=3 threshold")
    reset_all_states()
    events.clear()
    await set_chaos(ChaosSetRequest(tool="lookup_booking", fault="ERROR_500", count=10))
    try:
        await execute_tool_call("lookup_booking", lookup_booking, "BKG123")
    except EscalationError:
        pass
    transitions = [e for e in events if e["event"] == "state_transition"]
    transition_chain = [(t["from"], t["to"]) for t in transitions]
    print(f"  Transitions: {transition_chain}")
    assert ("HEALTHY", "DEGRADED") in transition_chain, f"Missing HEALTHY→DEGRADED in {transition_chain}"
    # With N=3, DEGRADED→CIRCUIT_OPEN should happen on the 3rd consecutive failure
    assert ("DEGRADED", "CIRCUIT_OPEN") in transition_chain, f"Missing DEGRADED→CIRCUIT_OPEN in {transition_chain}"
    print("  ✓ State machine transitions verified (N=3)")

    # Test 8: get_all_states returns all 4 tools
    print("\n[03-8] get_all_states")
    all_states = get_all_states()
    print(f"  Tools: {[s['tool'] for s in all_states]}")
    assert len(all_states) == 4
    print("  ✓ All 4 tool states present")

    # Test 9: get_aggregate_state
    print("\n[03-9] get_aggregate_state")
    reset_all_states()
    agg = get_aggregate_state()
    print(f"  Aggregate (all healthy): {agg['aggregate_state']}")
    assert agg["aggregate_state"] == "HEALTHY"
    # Make one tool escalated
    await set_chaos(ChaosSetRequest(tool="charge_fare_difference", fault="ERROR_500", count=10))
    try:
        await execute_tool_call("charge_fare_difference", charge_fare_difference, 50.0, "tok_123")
    except EscalationError:
        pass
    agg = get_aggregate_state()
    print(f"  Aggregate (one escalated): {agg['aggregate_state']}")
    assert agg["aggregate_state"] == "ESCALATED"
    assert agg["total_failures"] > 0
    assert len(agg["tool_states"]) == 4
    print("  ✓ Aggregate state reflects worst tool state")

    # Test 10: ValueError from Part 01 is NOT retried
    print("\n[03-10] ValueError passthrough (no retry)")
    reset_all_states()
    # Clear any leftover chaos from previous tests
    from backend.chaos_middleware import chaos_config as cc
    for key in cc:
        cc[key] = {"fault": "NONE", "remaining": 0}
    try:
        await execute_tool_call("lookup_booking", lookup_booking, "")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  Caught ValueError: {e}")
        state = get_tool_state("lookup_booking")
        assert state["state"] == "HEALTHY", "State should remain HEALTHY on input validation error"
        print("  ✓ ValueError passed through without retry or state change")

    # Test 11: Bounded retries — no infinite loop
    print("\n[03-11] Bounded retries (max 4 attempts)")
    reset_all_states()
    events.clear()
    await set_chaos(ChaosSetRequest(tool="lookup_booking", fault="ERROR_500", count=100))
    try:
        await execute_tool_call("lookup_booking", lookup_booking, "BKG123")
    except EscalationError as e:
        tool_call_events = [ev for ev in events if ev["event"] == "tool_call_started"]
        print(f"  Total attempts: {len(tool_call_events)}")
        assert len(tool_call_events) <= 4, f"Expected max 4 attempts, got {len(tool_call_events)}"
        print("  ✓ Retries bounded — no infinite loop")

    # Test 12: Every transition logged with all required fields
    print("\n[03-12] Event field completeness")
    reset_all_states()
    events.clear()
    await set_chaos(ChaosSetRequest(tool="check_availability", fault="ERROR_500", count=1))
    await execute_tool_call("check_availability", check_availability, "2026-09-15", "DEL-BOM")

    for ev in events:
        assert "ts" in ev, f"Missing timestamp in event: {ev}"
        assert "event" in ev, f"Missing event type: {ev}"
        if ev["event"] == "fault_detected":
            assert "tool" in ev and "fault_type" in ev, f"Missing fields in fault_detected: {ev}"
        if ev["event"] == "strategy_chosen":
            assert all(k in ev for k in ["tool", "strategy", "model", "reasoning"]), \
                f"Missing fields in strategy_chosen: {ev}"
        if ev["event"] == "state_transition":
            assert all(k in ev for k in ["tool", "from", "to"]), \
                f"Missing fields in state_transition: {ev}"
    print(f"  ✓ All {len(events)} events have required fields")

    print("\n✅ All Part 03 tests passed!")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    await test_plan_next_action()
    await test_resilience_core()
    print("\n" + "=" * 60)
    print("🎉  ALL TESTS PASSED — Parts 03 & 04 verified!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
