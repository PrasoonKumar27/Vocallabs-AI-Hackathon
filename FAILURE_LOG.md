# Failure Log

## What we tried that didn't work
- **The Initial Fallback Planner Loop:** Our initial fallback rule-based planner (`model_router.py`) checked if a tool was in the success `results` dictionary to decide what to run next. When a tool like `charge_fare_difference` failed and triggered an escalation, it was skipped by the orchestrator but the planner kept recommending it because it hadn't succeeded. This caused an infinite loop where the system kept fetching the same failed plan 10 times until the orchestrator's max-step limit was hit. We fixed this by making the planner aware of the `escalated_tools` state.
- **Eval Suite Timing vs Real Latencies:** We originally specified random delays of 5 to 15 seconds for `LATENCY_SPIKE`. This meant our 22-scenario eval suite—containing multiple latency faults and exponential backoffs for rate limits—took over 90 seconds, causing the HTTP clients polling the suite to timeout. We tightened the latency spike to 4.1 seconds (just over the 4-second wall-clock detection threshold) to keep the eval suite under 60 seconds without faking the test logic.

## What the system still gets wrong
- **Test-Induced Determinism:** To reliably evaluate the Payment Safety Net (which forces an escalation if `charge_fare_difference` fails twice), we had to remove the random price calculation from our mock `check_availability` tool. If the price difference was negative, the rule-based planner would legitimately skip the payment tool, causing the safety net eval (`s21`) to fail as the tool was never called. The system currently struggles to evaluate conditional tool paths unless we artificially force the conditions.
- **Silent Null Deep Nesting:** `SILENT_NULL` currently returns an empty dictionary. The payload corruptor doesn't aggressively prune deeply nested sub-fields; it corrupts top-level primitives.

## Known demo risks
- **Complete Provider Outage:** If both the primary and secondary models go down simultaneously, the system falls back to a static rule-based planner. While it prevents crashing, it loses the dynamic reasoning capabilities the dashboard highlights (the strategy reasoning simply reads generic fallback messages).
- **Rapid-Clicking the Chaos Console:** While the frontend disables the button during the `POST` request, mashing multiple faults for the same tool rapidly across multiple tabs could create race conditions in the in-memory `chaos_config` dictionary.

## What we'd fix with another week
- **Move state to Redis:** The in-memory `ToolState` tracker and `chaos_config` work for a single-server demo, but they prevent horizontal scaling. Moving them to Redis would allow multi-tenant sessions and concurrent multi-judge demos.
- **Enhanced Dashboard Analytics:** The Eval Scoreboard is currently a manual run. We'd convert this into a continuous background heartbeat that plots the `avg_recovery_ms` over time on a live chart.
- **Parallel Tool Execution:** The orchestrator strictly runs one tool at a time sequentially. A real-world agent might need to perform `lookup_booking` and `check_availability` in parallel before deciding on the payment.

## Eval harness results at freeze
* **Passed:** 22 / 22
* **Average recovery time:** 3346ms
* **Scenarios still failing:** None. (All 22 scenarios pass reliably following the deterministic price-delta fix).
