# ToolFall

ToolFall is a resilience layer for AI agents that use external tools. Most "AI agent" demos assume every tool call succeeds — ours assumes the opposite. A live Chaos Console lets you inject real failures (server errors, corrupted responses, silent nulls, latency spikes, rate limits) into any step of a multi-step customer-support task, and watch a model-driven resilience core decide in real time whether to retry, back off, switch to a secondary model, fall back to cached data, or escalate to a human — never silently failing. Two genuinely different models cooperate: one plans the task, the other takes over live if the first is slow, down, or wrong.

## Architecture

```text
                         ┌─────────────────────────┐
                         │   Chaos Console (UI)    │
                         │ toggles per-tool faults │
                         └────────────┬────────────┘
                                      │ sets chaos config
                                      ▼
┌──────────────┐   plans task   ┌───────────────────┐   tool call   ┌────────────────────┐
│ Primary Model│───────────────▶│ Task Orchestrator │──────────────▶│  Chaos Middleware  │
│ (Model A)    │◀───────────────│ (agent loop)      │◀──────────────│  (injects faults)  │
└──────────────┘   next action  └─────────┬─────────┘   response    └──────────┬─────────┘
       ▲                                  │                                    │
       │ escalate on low                  ▼                                    ▼
       │ confidence / timeout     ┌─────────────────┐                 ┌────────────────┐
       │                          │ ToolFall Core   │                 │ Mock Tool APIs │
┌──────┴────────┐                 │(resilience state│◀──────────────│ booking/pay/etc│
│ Secondary Mod │◀────────────────│ machine + strat │                 └────────────────┘
│ (Model B,     │  strategy calls │ selector)       │
│ fallback)     │────────────────▶└─────────┬───────┘
└───────────────┘                           │
                                            ▼
                                ┌───────────────────────┐
                                │ Eval Harness / Logger │
                                │(20 chaos scenarios,   │
                                │ pass/fail, latency)   │
                                └───────────────────────┘
```

## Running ToolFall

ToolFall runs entirely locally. You need Python 3.10+ and Node.js installed.

1. **Start the Backend:**
   ```bash
   cd backend
   pip install -r requirements.txt
   python -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```

2. **Start the Frontend:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. **View the Dashboard:** Open [http://localhost:3000](http://localhost:3000)

## Hackathon Constraints Satisfied

*   **No Crash Allowed:** A robust state-machine ensures failures trigger structured fallback strategies or controlled escalations without killing the execution loop.
*   **Visible Fallback:** The frontend live-traces the strategy chosen by the model with specific UI callouts when failovers occur.
*   **Two Different Models:** Gemini serves as the primary task planner and strategist. A strict rule-based fallback model acts as the secondary, ensuring the agent remains functional even during total provider outages.
*   **Simulated Real-World Constraints:** The backend mocks 4 distinct APIs, each with native latencies, supporting 6 distinct failure types triggered instantly via the Chaos Console.

## The Five Questions

1. **What problem, and who exactly has it?**
   An engineer shipping an AI agent into production — for example at a company whose voice/chat agents depend on real-time calls to booking, payment, and CRM systems — who has watched an agent silently break or report false success when a downstream API returns garbage.
2. **What is the non-obvious hard part?**
   Telling apart a fault that's safe to retry from one that must escalate — a payment call failing silently is not the same risk as a notification call failing — and making that call with a model rather than a static rule table, without the model itself becoming a new point of failure.
3. **What did you build versus what did the API give you?**
   The API gives a single tool call and a single response. We built the supervising layer around it: fault classification, a bounded state machine, a model-driven strategy selector, a second model as a live failover path, and an evaluation harness that scores resilience numerically across 20+ scenarios.
4. **Why does this break if you remove the AI?**
   Without a model in the loop, fault handling collapses to a fixed if/else that can't weigh "this is the 2nd payment failure, escalate" against "this is the 1st notification failure, retry" using task context — only the error code.
5. **What breaks at ten thousand users?**
   The in-memory state and single-process WebSocket fan-out don't horizontally scale (would need Redis for shared state); a model call on every single fault adds real latency/cost at volume, which is exactly why the hard-coded payment-escalation safety net exists as a cost/latency circuit-breaker rather than relying on a model call for every failure.

## Prior Art Check (Hour 2 Search)

*   **ChaosEater (Automated LLM Chaos Testing):** ChaosEater is an offline testing framework for analyzing LLM reactions to injected faults. *ToolFall differs* by acting as a live, run-time resilience layer that intercepts and catches failures in production.
*   **LangChain / ReAct Error Handlers:** Basic framework features allow feeding parsing errors back to the LLM. *ToolFall differs* by separating infrastructure retries from logical model-driven recovery using a dual-model circuit breaker.
*   **NeMo Guardrails:** Focuses on output validation and semantic routing. *ToolFall differs* by governing API interaction execution flow rather than just generative content filtering.

## Failure Log
Read about what worked, what didn't, and our strict eval metrics in [FAILURE_LOG.md](FAILURE_LOG.md).
