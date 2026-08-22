"""
Part 03 — Resilience Core

State machine + strategy selector. This is the centerpiece of ToolFall.

Owns the per-tool circuit-breaker state machine:
    HEALTHY → DEGRADED → CIRCUIT_OPEN → RECOVERING → (HEALTHY or CIRCUIT_OPEN)
    with a parallel terminal state ESCALATED.

Supervises every tool call: wraps call_with_chaos, detects faults (exceptions,
empty/corrupt payloads), consults the model router for a strategy decision,
and executes that decision (retry, backoff, cache, escalate).

Parts 05/07 interact with this through execute_tool_call() and read state
via get_tool_state() / get_all_states().
"""

import asyncio
import copy
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.chaos_middleware import (
    RateLimitError,
    ServerError500,
    call_with_chaos,
)
from backend.model_router import decide_strategy

logger = logging.getLogger("toolfall.resilience_core")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_STATES = {"HEALTHY", "DEGRADED", "CIRCUIT_OPEN", "RECOVERING", "ESCALATED"}
MAX_RETRIES = 4  # max total attempts (initial + 3 retries)
CIRCUIT_OPEN_COOLDOWN = 5.0  # seconds before CIRCUIT_OPEN → RECOVERING probe
CACHE_TTL = 300  # seconds

# Tool → stakes mapping (payment is "high", everything else is "normal" per spec)
TOOL_STAKES: dict[str, str] = {
    "lookup_booking": "normal",
    "check_availability": "normal",
    "charge_fare_difference": "high",
    "send_confirmation": "normal",
}

# LATENCY_SPIKE detection threshold (seconds) — if a tool call takes longer
# than this even without raising an exception, classify as LATENCY_SPIKE
LATENCY_SPIKE_THRESHOLD = 4.0

# Payment safety net: force escalation after this many consecutive failures
# on charge_fare_difference, regardless of model decision (disclosed design choice)
PAYMENT_FORCE_ESCALATE_AFTER = 2

# ---------------------------------------------------------------------------
# Event callback — Part 05 sets this to push events to the WebSocket bus
# ---------------------------------------------------------------------------
_event_callback: Optional[Callable] = None


def set_event_callback(cb):
    """Register an async callback for resilience events (state transitions, etc.)."""
    global _event_callback
    _event_callback = cb


async def _emit(event: dict):
    """Push event to the callback if registered, otherwise just log."""
    logger.info("Event: %s", event)
    if _event_callback:
        await _event_callback(event)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Per-tool state tracking
# ---------------------------------------------------------------------------
class ToolState:
    """Circuit-breaker state machine for a single tool."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.state = "HEALTHY"
        self.consecutive_failures = 0
        self.total_calls = 0
        self.total_failures = 0
        self.last_failure_ts: Optional[float] = None
        self.last_success_ts: Optional[float] = None
        self.last_fault_type: Optional[str] = None
        self.cache: Optional[dict] = None
        self.cache_ts: Optional[float] = None

    async def transition(self, new_state: str):
        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid state: {new_state}")
        if new_state == self.state:
            return
        old = self.state
        self.state = new_state
        await _emit({
            "event": "state_transition",
            "tool": self.tool_name,
            "from": old,
            "to": new_state,
            "ts": _iso_now(),
        })

    def record_success(self):
        self.consecutive_failures = 0
        self.last_success_ts = time.monotonic()
        self.total_calls += 1

    def record_failure(self, fault_type: str):
        self.consecutive_failures += 1
        self.total_failures += 1
        self.total_calls += 1
        self.last_failure_ts = time.monotonic()
        self.last_fault_type = fault_type

    def update_cache(self, result: dict):
        """Store last-known-good result."""
        self.cache = copy.deepcopy(result)
        self.cache_ts = time.monotonic()

    def get_stale_cache(self) -> Optional[dict]:
        if self.cache is None:
            return None
        age = time.monotonic() - (self.cache_ts or 0)
        if age > CACHE_TTL:
            return None
        return copy.deepcopy(self.cache)

    def to_dict(self) -> dict:
        return {
            "tool": self.tool_name,
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "last_fault_type": self.last_fault_type,
        }


# Global per-tool states
_tool_states: dict[str, ToolState] = {
    "lookup_booking": ToolState("lookup_booking"),
    "check_availability": ToolState("check_availability"),
    "charge_fare_difference": ToolState("charge_fare_difference"),
    "send_confirmation": ToolState("send_confirmation"),
}


def get_tool_state(tool_name: str) -> dict:
    """Return serializable state for a single tool."""
    if tool_name not in _tool_states:
        raise ValueError(f"Unknown tool: {tool_name}")
    return _tool_states[tool_name].to_dict()


def get_all_states() -> list[dict]:
    """Return serializable states for all tools."""
    return [ts.to_dict() for ts in _tool_states.values()]


def get_aggregate_state() -> dict:
    """
    Return an aggregate task-level state for the dashboard.
    The aggregate is the "worst" state across all tools:
    ESCALATED > CIRCUIT_OPEN > RECOVERING > DEGRADED > HEALTHY
    """
    priority = {"HEALTHY": 0, "DEGRADED": 1, "RECOVERING": 2, "CIRCUIT_OPEN": 3, "ESCALATED": 4}
    worst_state = "HEALTHY"
    worst_priority = 0
    total_calls = 0
    total_failures = 0
    for ts in _tool_states.values():
        p = priority.get(ts.state, 0)
        if p > worst_priority:
            worst_priority = p
            worst_state = ts.state
        total_calls += ts.total_calls
        total_failures += ts.total_failures
    return {
        "aggregate_state": worst_state,
        "total_calls": total_calls,
        "total_failures": total_failures,
        "tool_states": get_all_states(),
    }


def reset_all_states():
    """Reset all tool states to HEALTHY (useful between eval runs)."""
    for name in list(_tool_states.keys()):
        _tool_states[name] = ToolState(name)


# ---------------------------------------------------------------------------
# Fault detection helpers
# ---------------------------------------------------------------------------

def _classify_fault_from_exception(exc: Exception) -> str:
    """Map an exception to one of the chaos fault types."""
    if isinstance(exc, ServerError500):
        return "ERROR_500"
    if isinstance(exc, RateLimitError):
        return "RATE_LIMIT"
    if isinstance(exc, asyncio.TimeoutError):
        return "LATENCY_SPIKE"
    return "ERROR_500"  # generic


def _detect_payload_fault(result: Any, tool_name: str) -> Optional[str]:
    """
    Inspect a returned result for SILENT_NULL or CORRUPT_PAYLOAD signs.
    Returns fault_type string or None if the result looks clean.
    """
    if result is None or result == {}:
        return "SILENT_NULL"

    if not isinstance(result, dict):
        return "CORRUPT_PAYLOAD"

    # Schema checks per tool
    expected_keys = {
        "lookup_booking": {"booking_id", "passenger_name", "route", "date", "fare"},
        "check_availability": {"available", "seats_left", "price_delta"},
        "charge_fare_difference": {"charged", "transaction_id", "amount"},
        "send_confirmation": {"sent", "message_id"},
    }

    required = expected_keys.get(tool_name, set())
    if required and not required.issubset(result.keys()):
        return "CORRUPT_PAYLOAD"

    # Type checks for known critical fields
    type_checks = {
        "lookup_booking": {"fare": (int, float), "booking_id": str},
        "check_availability": {"available": bool, "seats_left": int, "price_delta": (int, float)},
        "charge_fare_difference": {"charged": bool, "amount": (int, float)},
        "send_confirmation": {"sent": bool, "message_id": str},
    }
    checks = type_checks.get(tool_name, {})
    for field, expected_type in checks.items():
        if field in result and not isinstance(result[field], expected_type):
            return "CORRUPT_PAYLOAD"

    return None


# ---------------------------------------------------------------------------
# State machine transition logic
# ---------------------------------------------------------------------------

async def _update_state_on_failure(ts: ToolState):
    """Drive state transitions after a failure."""
    if ts.state == "HEALTHY":
        await ts.transition("DEGRADED")
    elif ts.state == "DEGRADED" and ts.consecutive_failures >= 3:
        await ts.transition("CIRCUIT_OPEN")
    elif ts.state == "RECOVERING":
        # Recovery probe failed → back to CIRCUIT_OPEN
        await ts.transition("CIRCUIT_OPEN")


async def _update_state_on_success(ts: ToolState):
    """Drive state transitions after a success."""
    if ts.state in ("DEGRADED", "RECOVERING"):
        await ts.transition("HEALTHY")
    elif ts.state == "CIRCUIT_OPEN":
        # Shouldn't normally get here, but handle gracefully
        await ts.transition("HEALTHY")


# ---------------------------------------------------------------------------
# Core public function: execute a tool call with full resilience
# ---------------------------------------------------------------------------

async def execute_tool_call(
    tool_name: str,
    real_fn: Callable,
    *args,
    **kwargs,
) -> dict:
    """
    Execute a tool call with chaos injection, fault detection, and resilience.

    This is what Parts 05 (orchestrator) calls — never call_with_chaos or
    the raw tool function directly.

    Returns the tool result dict on success (may include _degraded=True for cached data).
    Raises EscalationError if the call is routed to human review.
    """
    if tool_name not in _tool_states:
        raise ValueError(f"Unknown tool: {tool_name}")

    ts = _tool_states[tool_name]
    stakes = TOOL_STAKES.get(tool_name, "normal")

    attempt = 0
    last_fault_type = None

    while attempt < MAX_RETRIES:
        attempt += 1

        # If circuit is open, wait before probing
        if ts.state == "CIRCUIT_OPEN":
            logger.info("[%s] Circuit open — waiting %.1fs before recovery probe", tool_name, CIRCUIT_OPEN_COOLDOWN)
            await asyncio.sleep(CIRCUIT_OPEN_COOLDOWN)
            await ts.transition("RECOVERING")

        # Emit tool_call_started
        await _emit({
            "event": "tool_call_started",
            "tool": tool_name,
            "attempt": attempt,
            "ts": _iso_now(),
        })

        fault_type = None
        result = None

        try:
            # Time the call for LATENCY_SPIKE detection
            call_start = time.monotonic()
            result = await call_with_chaos(tool_name, real_fn, *args, **kwargs)
            call_duration = time.monotonic() - call_start

            # Detect LATENCY_SPIKE even if no exception was raised
            if call_duration > LATENCY_SPIKE_THRESHOLD:
                fault_type = "LATENCY_SPIKE"
                await _emit({
                    "event": "fault_detected",
                    "tool": tool_name,
                    "fault_type": fault_type,
                    "ts": _iso_now(),
                })
                ts.record_failure(fault_type)
                await _update_state_on_failure(ts)
                # We still got a result — cache it but treat it as a fault
                if result and isinstance(result, dict) and _detect_payload_fault(result, tool_name) is None:
                    ts.update_cache(result)
            else:
                # Check for silent payload faults
                payload_fault = _detect_payload_fault(result, tool_name)
                if payload_fault:
                    fault_type = payload_fault
                    await _emit({
                        "event": "fault_detected",
                        "tool": tool_name,
                        "fault_type": fault_type,
                        "ts": _iso_now(),
                    })
                    ts.record_failure(fault_type)
                    await _update_state_on_failure(ts)
                else:
                    # Clean success
                    ts.record_success()
                    ts.update_cache(result)
                    await _update_state_on_success(ts)
                    return result

        except (ServerError500, RateLimitError, asyncio.TimeoutError) as exc:
            fault_type = _classify_fault_from_exception(exc)
            await _emit({
                "event": "fault_detected",
                "tool": tool_name,
                "fault_type": fault_type,
                "ts": _iso_now(),
            })
            ts.record_failure(fault_type)
            await _update_state_on_failure(ts)

        except ValueError:
            # Input validation errors from Part 01 — don't retry, re-raise
            raise

        except Exception as exc:
            fault_type = "ERROR_500"
            await _emit({
                "event": "fault_detected",
                "tool": tool_name,
                "fault_type": fault_type,
                "ts": _iso_now(),
            })
            ts.record_failure(fault_type)
            await _update_state_on_failure(ts)

        # ---- Payment safety net (hard-coded, disclosed design choice) ----
        # If charge_fare_difference has failed 2+ consecutive times, force
        # ESCALATE_TO_HUMAN regardless of what the model suggests.
        last_fault_type = fault_type
        if (
            tool_name == "charge_fare_difference"
            and ts.consecutive_failures >= PAYMENT_FORCE_ESCALATE_AFTER
        ):
            forced_reasoning = (
                f"Payment safety net: {ts.consecutive_failures} consecutive failures "
                f"on charge_fare_difference — forced escalation (model decision overridden)."
            )
            logger.warning("[%s] PAYMENT SAFETY NET triggered — forcing ESCALATE_TO_HUMAN", tool_name)
            await _emit({
                "event": "strategy_chosen",
                "tool": tool_name,
                "strategy": "ESCALATE_TO_HUMAN",
                "seconds": None,
                "model": "safety_net",
                "reasoning": forced_reasoning,
                "ts": _iso_now(),
            })
            await ts.transition("ESCALATED")
            await _emit({
                "event": "escalated",
                "tool": tool_name,
                "reason": f"{ts.consecutive_failures} consecutive failures on high-stakes call (payment safety net)",
                "ts": _iso_now(),
            })
            raise EscalationError(
                tool_name=tool_name,
                fault_type=fault_type,
                attempts=attempt,
                reasoning=forced_reasoning,
            )

        # ---- Fault detected — ask model router for strategy ----
        fault_context = {
            "tool": tool_name,
            "fault_type": fault_type,
            "attempt": attempt,
            "task_stakes": stakes,
        }

        strategy_resp = await decide_strategy(fault_context)
        strategy = strategy_resp["strategy"]
        backoff_seconds = strategy_resp.get("backoff_seconds")
        reasoning = strategy_resp.get("reasoning", "")

        await _emit({
            "event": "strategy_chosen",
            "tool": tool_name,
            "strategy": strategy,
            "seconds": backoff_seconds,
            "model": strategy_resp.get("model_used", "unknown"),
            "reasoning": reasoning,
            "ts": _iso_now(),
        })

        logger.info(
            "[%s] attempt=%d fault=%s → strategy=%s (%s)",
            tool_name, attempt, fault_type, strategy, reasoning,
        )

        # ---- Execute the chosen strategy ----
        if strategy == "ESCALATE_TO_HUMAN":
            await ts.transition("ESCALATED")
            await _emit({
                "event": "escalated",
                "tool": tool_name,
                "reason": f"{ts.consecutive_failures} consecutive failures on {stakes}-stakes call",
                "ts": _iso_now(),
            })
            raise EscalationError(
                tool_name=tool_name,
                fault_type=fault_type,
                attempts=attempt,
                reasoning=reasoning,
            )

        elif strategy == "USE_STALE_CACHE":
            cached = ts.get_stale_cache()
            if cached is not None:
                logger.info("[%s] Serving stale cache (tagged as degraded)", tool_name)
                cached["_degraded"] = True  # tag as degraded data
                return cached
            # No cache available — fall through to retry
            logger.warning("[%s] USE_STALE_CACHE chosen but no cache available — retrying instead", tool_name)

        elif strategy == "RETRY_BACKOFF":
            wait = backoff_seconds if backoff_seconds and backoff_seconds > 0 else 2.0
            logger.info("[%s] Backing off %.1fs", tool_name, wait)
            await asyncio.sleep(wait)
            # loop continues to next attempt

        elif strategy == "RETRY_IMMEDIATE":
            # loop continues immediately
            pass

        elif strategy == "SWITCH_MODEL":
            # For tool-level faults, SWITCH_MODEL doesn't directly help,
            # but we honour the model's decision and retry with the hope
            # that the next plan_next_action call will use the secondary.
            pass

    # Exhausted all retries
    await ts.transition("ESCALATED")
    await _emit({
        "event": "escalated",
        "tool": tool_name,
        "reason": f"Exhausted {MAX_RETRIES} attempts on {stakes}-stakes call (last fault: {last_fault_type})",
        "ts": _iso_now(),
    })
    raise EscalationError(
        tool_name=tool_name,
        fault_type=last_fault_type or "UNKNOWN",
        attempts=attempt,
        reasoning=f"Exhausted all {MAX_RETRIES} retry attempts.",
    )


# ---------------------------------------------------------------------------
# Custom exception for escalation
# ---------------------------------------------------------------------------

class EscalationError(Exception):
    """Raised when a tool call is escalated to human review."""

    def __init__(self, tool_name: str, fault_type: str, attempts: int, reasoning: str):
        self.tool_name = tool_name
        self.fault_type = fault_type
        self.attempts = attempts
        self.reasoning = reasoning
        super().__init__(
            f"Escalated {tool_name} to human review after {attempts} attempts "
            f"(fault: {fault_type}): {reasoning}"
        )
