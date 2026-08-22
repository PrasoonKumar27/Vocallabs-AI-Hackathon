"""
Part 06 — Eval Harness Runner

Executes the chaos test scenarios against the live system and scores
the resilience logic. Exposed via GET /api/eval/run.
"""

import asyncio
import time
import httpx
from fastapi import APIRouter

from backend.eval.scenarios import SCENARIOS

router = APIRouter()

# In production this would be configurable, but for the hackathon
# we assume the eval harness runs in the same process/network as the backend
BASE_URL = "http://127.0.0.1:8000"

async def _run_scenario(scenario: dict, client: httpx.AsyncClient) -> dict:
    """Run a single scenario and evaluate the outcome."""
    start_time = time.time()
    
    tool = scenario["tool"]
    fault = scenario["fault"]
    count = scenario["count"]
    expect = scenario["expect"]
    
    # 1. Set Chaos
    chaos_resp = await client.post(f"{BASE_URL}/api/chaos/set", json={
        "tool": tool,
        "fault": fault,
        "count": count
    })
    chaos_resp.raise_for_status()
    
    # 2. Start Task
    start_resp = await client.post(f"{BASE_URL}/api/task/start", json={
        "request": f"Reschedule BKG_{scenario['id']} to 2026-12-01"
    })
    start_resp.raise_for_status()
    task_id = start_resp.json()["task_id"]
    
    # 3. Poll for completion (up to 30s)
    completed_event = None
    events = []
    
    for _ in range(60): # 30s timeout
        events_resp = await client.get(f"{BASE_URL}/api/task/{task_id}/events")
        if events_resp.status_code == 200:
            events = events_resp.json().get("events", [])
            if events and events[-1].get("event") == "task_completed":
                completed_event = events[-1]
                break
        await asyncio.sleep(0.5)
        
    end_time = time.time()
    recovery_ms = int((end_time - start_time) * 1000)
    
    passed = False
    notes = ""
    
    if not completed_event:
        passed = False
        notes = "Timed out waiting for task_completed event."
    else:
        success = completed_event.get("success")
        degraded = completed_event.get("degraded")
        
        if expect == "RECOVER":
            if success is True and degraded is False:
                passed = True
                notes = "Recovered cleanly."
            else:
                passed = False
                notes = f"Expected clean recovery. Got success={success}, degraded={degraded}."
                
        elif expect == "RECOVER_SLOW":
            if success is True:
                passed = True
                notes = "Recovered (with expected latency)."
            else:
                passed = False
                notes = f"Expected slow recovery. Got success={success}."
                
        elif expect == "DEGRADED":
            if success is True and degraded is True:
                passed = True
                notes = "Recovered via degraded path (e.g. cache)."
            else:
                passed = False
                notes = f"Expected degraded recovery. Got success={success}, degraded={degraded}."
                
        elif expect == "ESCALATE":
            # Must emit an escalated event for the target tool
            escalated_events = [
                e for e in events 
                if e.get("event") == "escalated" and e.get("tool") == tool
            ]
            
            if escalated_events:
                passed = True
                notes = f"Escalated correctly: {escalated_events[0].get('reason')}"
            else:
                passed = False
                notes = "Did not emit escalated event for the target tool."
                
    return {
        "id": scenario["id"],
        "passed": passed,
        "recovery_ms": recovery_ms,
        "notes": notes
    }


@router.get("/api/eval/run")
async def run_eval_suite():
    """
    Run all scenarios sequentially. Returns the full suite score.
    """
    results = []
    
    # We use a custom timeout because LATENCY_SPIKE can take up to 15s
    timeout = httpx.Timeout(45.0)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Reset all chaos before starting
        tools = ["lookup_booking", "check_availability", "charge_fare_difference", "send_confirmation"]
        for t in tools:
            await client.post(f"{BASE_URL}/api/chaos/set", json={"tool": t, "fault": "NONE", "count": 0})
            
        for scenario in SCENARIOS:
            res = await _run_scenario(scenario, client)
            results.append(res)
            
            # Reset chaos for the tool to avoid bleed-over if it didn't consume its count
            await client.post(f"{BASE_URL}/api/chaos/set", json={"tool": scenario["tool"], "fault": "NONE", "count": 0})

    passed_count = sum(1 for r in results if r["passed"])
    total_time = sum(r["recovery_ms"] for r in results)
    
    return {
        "passed": passed_count,
        "total": len(SCENARIOS),
        "avg_recovery_ms": int(total_time / len(results)) if results else 0,
        "results": results
    }
