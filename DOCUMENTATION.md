# ToolFall System Documentation

This document provides a comprehensive technical overview of ToolFall, designed to meet the exact evaluation criteria for the Vocallabs AI Hackathon.

---

## 1. What We Built and How It Works

**What We Built:**
ToolFall is a resilience layer and orchestration engine for AI agents that use external tools. Most "AI agent" demos and frameworks assume every tool call succeeds. ToolFall assumes the opposite. We built a system that wraps around an agent's tool calls and provides a model-driven circuit breaker that catches failures (server errors, rate limits, latency spikes) and decides in real-time how to recover, ensuring the agent **never crashes**. 

**How It Works:**
The system uses a decoupled architecture:
- **Backend (FastAPI):** Hosts the orchestration loop, simulated mock APIs, and a WebSocket server. It intercepts every tool call an agent makes. If a mock API throws an error (injected via the UI), the backend pauses the agent and engages the **ToolFall Core**.
- **ToolFall Core (The Resilience Layer):** It asks the **Primary AI Model (Gemini)** to evaluate the error context and choose a strategy (`RETRY`, `BACKOFF`, `ESCALATE`). 
- **Dual-Model Failover:** If the Primary Model itself crashes, times out, or fails to parse, control immediately shifts to a **Secondary Rule-Based Model** which takes over the recovery process, preventing a total system crash.
- **Frontend (Next.js 14):** A beautiful 3D, glassmorphism-styled Chaos Console that visualizes the state machine in real-time. Users can manually inject faults into specific tools and watch the agent adapt.

---

## 2. My Contribution and Work Done

As the lead developer (Prasoon Kumar), I built this entire system from scratch for the hackathon. My contributions spanned the full stack:

- **Backend Development:** Engineered the Python FastAPI backend, including the async WebSocket architecture and the custom state machine that governs tool transitions (`HEALTHY`, `DEGRADED`, `CIRCUIT_OPEN`).
- **AI Integration:** Implemented the dual-model failover logic, ensuring the Primary Gemini model could parse failure context and that the system gracefully degraded to the Secondary model during critical failures.
- **Frontend Development:** Designed and built the Next.js React frontend from the ground up. I implemented the real-time Chaos Console, narrative event timeline, and advanced CSS 3D/glassmorphism animations.
- **DevOps & Deployment:** Containerized the backend using Docker, wrote the deployment scripts, and successfully deployed the backend to Railway and the frontend to Vercel.
- **Evaluation Framework:** Wrote the 22-scenario automated testing harness that proves the system's 100% crash-resistance.

---

## 3. Team Roles and Contributions

*(Note: This project was developed as a solo submission by Prasoon Kumar. All frontend, backend, AI orchestration, and design work was completed individually.)*

---

## 4. Key Features, Technical Decisions, and Challenges

### Key Features
- **🎮 Live Chaos Console:** Real-time injection of 5 distinct failure types (500 Server Errors, Latency Spikes, Corrupt Payloads, Rate Limits, Silent Nulls) into active AI workflows.
- **🔄 Dual-Model Circuit Breaker:** A seamless failover mechanism from a heavy LLM (Gemini) to a fast, rule-based fallback model.
- **📊 3D Cinematic UI:** A visually stunning frontend featuring glassmorphism, 3D card tilt effects, and real-time state visualizers designed to make complex agent behavior easy to understand.
- **🛡️ 100% Crash Resistance:** Achieved a perfect 22/22 pass rate on the evaluation harness by ensuring all unhandled exceptions are caught and routed to the escalation state machine.

### Technical Decisions
- **WebSockets over REST polling:** Chose WebSockets for the frontend-backend communication because the UI needed to instantly react to micro-state changes (like a 500ms latency spike or a fast model failover) without the overhead of HTTP polling.
- **FastAPI over Flask/Django:** Selected FastAPI for its native `asyncio` support, which was critical for handling parallel API calls, `async` model generation, and concurrent WebSocket connections without blocking the event loop.
- **Rule-Based Secondary Model:** Decided *not* to use a second LLM (like Claude/OpenAI) for the fallback model. If an API provider is down, network issues might take out multiple providers. A strict, local rule-based heuristic guarantees recovery with 0ms network latency.

### Challenges Faced
- **Handling Asynchronous State:** One of the hardest challenges was managing the agent's execution loop while waiting for the user to inject faults via the UI. I solved this by decoupling the task runner from the WebSocket broadcaster using Python's `asyncio.Queue` and shared memory state.
- **Vercel Deployment Constraints:** Vercel's strict routing and build rules conflicted with the monorepo structure. I overcame this by heavily configuring the `next.config.ts`, `vercel.json`, and adjusting all absolute imports to relative imports so the frontend could build in isolation.
- **Railway Port Binding:** Railway's dynamic `$PORT` injection failed to evaluate correctly in standard Docker `CMD` arrays. I solved this by writing a custom bash entrypoint (`start.sh`) that forces bash evaluation of the environment variables before booting Uvicorn.
