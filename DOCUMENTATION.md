# ToolFall System Documentation

This document provides a comprehensive technical overview of the ToolFall architecture, state machine, AI model fallbacks, and API interactions.

## 1. System Architecture Overview

ToolFall uses a modern, decoupled architecture:
- **Frontend (Next.js 14):** A React-based UI that visualizes the state of the AI agent using WebSockets. It includes the Main Task View, the Chaos Console, and the Eval Scoreboard.
- **Backend (FastAPI):** A high-performance asynchronous Python backend that hosts the agent orchestration loop, the tool mock APIs, the evaluation harness, and the WebSocket server.
- **Primary AI (Google Gemini):** The primary brain of the agent responsible for planning and executing the multi-step support task.
- **Secondary AI (Rule-Based / Light Model):** The fallback brain that guarantees the agent never crashes if the primary API fails, times out, or gets rate-limited.

---

## 2. The Agent State Machine

The core innovation of ToolFall is the strict state machine governing every tool call. Instead of letting the AI blindly call tools, every interaction goes through the `ToolFall Core` resilience layer.

### Tool States
A tool can be in one of the following states:
- `HEALTHY`: Normal operation.
- `DEGRADED`: A failure was detected; the system is applying a backoff/retry strategy.
- `CIRCUIT_OPEN`: Repeated failures have tripped the circuit breaker.
- `RECOVERING`: A test call is being made to check if the tool is healthy again.
- `ESCALATED`: The system has explicitly decided the failure cannot be handled automatically and requires human intervention.

### Failure Classification
When an error occurs, the system classifies it into one of the following Fault Types:
1. `ERROR_500`: Standard server crash.
2. `RATE_LIMIT`: API quota exceeded.
3. `LATENCY_SPIKE`: Timeout or slow response.
4. `SILENT_NULL`: An empty response body.
5. `CORRUPT_PAYLOAD`: Malformed JSON or garbage data.

---

## 3. The Dual-Model Failover Protocol

ToolFall is designed to never crash. It achieves this using a **Dual-Model Circuit Breaker**.

### The Primary Model (Gemini)
When a fault occurs, the orchestration loop pauses and passes the fault context to the Primary Model. The model is prompted to choose a resilience strategy based on the business logic of the specific tool:
- `RETRY_IMMEDIATE`: For transient errors (e.g., occasional 500s).
- `RETRY_WITH_BACKOFF`: For rate limits or latency spikes.
- `SERVE_CACHED`: For non-critical lookup tools.
- `ESCALATE_TO_HUMAN`: For critical tools (like payments) where guessing is dangerous.

### The Secondary Model (Fallback)
If the Primary Model itself fails (e.g., Gemini API is down, returns a 503, or times out), the system emits a `model_failover` event. 
The control flow immediately shifts to the **Secondary Model**. This model uses strict heuristics and lightweight logic to gracefully terminate or escalate the current step without crashing the orchestration loop.

---

## 4. API Reference

### REST Endpoints
- `GET /`: Root endpoint. Returns a basic status message.
- `GET /health`: Health check endpoint.
- `POST /task/start`: Initiates a new support task (e.g., rescheduling a booking). Returns a `task_id`.
- `POST /chaos/config`: Updates the global chaos configuration to inject specific faults into specific tools.

### WebSocket Events (`/ws/{task_id}`)
The frontend communicates with the backend via WebSockets to receive real-time updates. The UI reacts to the following event types:

1. `tool_call_started`: Emitted when the agent attempts to call a tool.
2. `fault_detected`: Emitted when a simulated mock API throws a predefined error.
3. `strategy_chosen`: Emitted when the Primary or Secondary model selects a recovery strategy. Includes the model's reasoning.
4. `state_transition`: Emitted when a tool's state changes (e.g., `HEALTHY` -> `DEGRADED`).
5. `model_failover`: Emitted when the Primary model goes down and the Secondary takes over.
6. `escalated`: Emitted when the task is passed to a human.
7. `task_completed`: Emitted at the end of the execution loop with success/failure metrics.

---

## 5. Evaluation Harness

The project includes an automated evaluation harness located at `/eval`. 
It runs **22 unique scenarios** designed to break standard LLM agents (e.g., sequential rate limits on booking APIs, followed by corrupt payloads on payment APIs). 
The scoring evaluates:
- **Crash Rate:** Did the python process throw an unhandled exception? (Must be 0%).
- **Logical Escalation:** Did it escalate payments instead of retrying blindly?
- **Failover Success:** Did the secondary model successfully take over when the primary was simulated to fail?

*Current Build Status: 22/22 (100%) Scenarios Passed.*
