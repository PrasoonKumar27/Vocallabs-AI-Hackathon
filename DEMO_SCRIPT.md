# Live Demo Script

> **Note for Presenters:** Rehearse this exact sequence at least twice before judging. Ensure the backend and frontend are actively running.

**Total Time: ~4.5 Minutes**

---

### 1. Frame It (30s)
*Open on the Task View dashboard without starting the task.*
**Speak:** "Most agent demos assume every API call succeeds. We built the opposite — a resilience layer that proves it survives failure, live, on demand."

### 2. Show the Architecture (30s)
*Switch briefly to the README or architecture diagram slide.*
**Speak:** 
* "The **Task Orchestrator** is our core agent loop."
* "Every tool call passes through the **Chaos Middleware**, allowing us to inject faults."
* "The **Resilience Core** manages state and decides how to recover when those faults hit."
* "And the **Dual-Model Router** ensures we have two separate brains — one planning, one as a live fallback."

### 3. Start the Task (60s)
*Switch back to the Task View. Click "▶ Start Task".*
**Action:** Let it run cleanly to completion. 
**Speak:** "We’ll reschedule booking BK123. Notice the live trace UI. On a happy path, the orchestrator plans the step, calls the tool, updates the status to HEALTHY, and completes the flow perfectly."

### 4. Inject a Fault via Chaos Console (90s)
*Open the Chaos Console in a side-by-side window or switch tabs.*
**Action:** Select `ERROR_500` under the `charge_fare_difference` (Payment API) row. Leave count at 1. Click "Inject". 
**Speak:** "Now for the fun part. I just armed a 500 Server Error to trigger the next time the agent tries to process a payment."
**Action:** Go back to the Task View and hit "▶ Start Task" again.
**Speak:** (Point at the trace UI as it happens) "Watch the trace. The fault is detected. Instantly, our model-driven strategist takes over. Look at the reasoning: it decided to retry immediately. It recovered without silently failing or crashing."

### 5. Trigger the Safety Net Escalation (60s)
*Go back to the Chaos Console.*
**Action:** Set "Fault count" to 2. Select `ERROR_500` under `charge_fare_difference` again. Click "Inject".
**Action:** Start the task again in the Task View.
**Speak:** "Models aren't perfect, and infinite retries on a payment gateway are dangerous. I've armed two consecutive payment failures. Watch the trace. The first fails and retries. The second fails... and boom. The Payment Safety Net circuit-breaker overrides the model. It halts the payment and flags it for human review. This is deliberate: high-stakes failures don't get retried forever."

### 6. Force Model Failover (30s)
*Highlight a prior model failover in the UI, or if configured, kill the primary API key in the terminal and restart the task.*
**Speak:** "If the primary AI model crashes or times out while trying to plan recovery, our system doesn't die. Notice the 'MODEL FAILOVER' callout in the trace. We have two genuinely different models cooperating—not just calling the same endpoint twice."

### 7. Show the Eval Scoreboard (30s)
*Click over to the Eval Scoreboard tab and hit "Run Eval Suite" (or show a pre-run result).*
**Speak:** "We don't just rely on manual clicks. This eval harness blasts 22 different chaos combinations across all tools—rate limits, null payloads, latency spikes. As you can see, 22 out of 22 survived with an average recovery time under 4 seconds. Our specific failure edge-cases are documented transparently in our Failure Log."

### 8. Q&A (30s+)
*Leave the dashboard up.*
**Speak:** "We're ready for your questions." *(Use the Five Questions guide in the README to field answers regarding scale, the hard part of state tracking, and why a static if/else fails).*
