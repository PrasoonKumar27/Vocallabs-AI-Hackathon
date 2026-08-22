"""
Part 05 — Task Orchestrator

The agent loop that drives the "reschedule my flight" task end to end.
Calls Part 04 to plan each step, routes every tool call through Part 03
(which uses Part 02 → Part 01), and emits every event to the WebSocket bus.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Callable

from backend.model_router import plan_next_action
from backend.resilience_core import (
    EscalationError,
    execute_tool_call,
    get_aggregate_state,
    reset_all_states,
)
from backend.tools.booking_api import lookup_booking
from backend.tools.availability_api import check_availability
from backend.tools.payment_api import charge_fare_difference
from backend.tools.notification_api import send_confirmation

logger = logging.getLogger("toolfall.orchestrator")

# Map tool name → actual async function
TOOL_REGISTRY: dict[str, Callable] = {
    "lookup_booking": lookup_booking,
    "check_availability": check_availability,
    "charge_fare_difference": charge_fare_difference,
    "send_confirmation": send_confirmation,
}

# The expected pipeline order (for reference / degraded-completion tracking)
PIPELINE_ORDER = [
    "lookup_booking",
    "check_availability",
    "charge_fare_difference",
    "send_confirmation",
]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_request(user_request: str) -> dict:
    """
    Extract booking_id, new_date, email, and payment_token from the
    user's free-text request. Falls back to sensible defaults so the
    demo always works even with a vague prompt.
    """
    booking_id = "BKG123"
    new_date = "2026-09-15"
    email = None
    payment_token = "tok_live_demo"

    # Try to extract booking ID (e.g. BKG123, BKG456)
    bkg_match = re.search(r"(BKG\d+)", user_request, re.IGNORECASE)
    if bkg_match:
        booking_id = bkg_match.group(1).upper()

    # Try to extract date (ISO format or common patterns)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", user_request)
    if date_match:
        new_date = date_match.group(1)

    # Try to extract email
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", user_request)
    if email_match:
        email = email_match.group(0)

    return {
        "booking_id": booking_id,
        "new_date": new_date,
        "email": email,
        "payment_token": payment_token,
    }


async def run_task(task_id: str, user_request: str, emit: Callable):
    """
    Drive the "reschedule my flight" task from start to finish.

    Args:
        task_id: Unique identifier for this task run.
        user_request: The user's free-text request (e.g. "Reschedule BKG123 to 2026-09-15").
        emit: Async callable that sends one event dict over the task's WebSocket connections.

    The loop:
      1. Build task_state from user_request + results so far.
      2. decision = await plan_next_action(task_state)
      3. Execute the tool via resilience_core.execute_tool_call()
         (which internally handles chaos, fault detection, retries, escalation)
      4. Fold result into task_state or record escalation.
      5. Repeat until all steps complete or are escalated.
      6. Emit task_completed.
    """
    # Reset per-tool resilience states for a fresh run
    reset_all_states()

    parsed = _parse_request(user_request)
    results: dict[str, dict] = {}
    escalated_tools: dict[str, str] = {}
    degraded = False
    max_steps = 10  # Safety bound to prevent infinite loops

    logger.info("[%s] Task started: %s", task_id, user_request)

    for step in range(max_steps):
        # Build task state for the model planner
        task_state = {
            "request": user_request,
            "booking_id": parsed["booking_id"],
            "new_date": parsed["new_date"],
            "payment_token": parsed["payment_token"],
            "results": results,
            "escalated": escalated_tools,
        }

        # If we have an email from the request, pass it through
        if parsed["email"]:
            task_state["email"] = parsed["email"]

        # Ask the model what to do next
        try:
            decision = await plan_next_action(task_state)
        except Exception as e:
            logger.error("[%s] plan_next_action failed: %s", task_id, e)
            await emit({
                "event": "task_completed",
                "success": False,
                "degraded": True,
                "error": f"Planning failed: {str(e)}",
                "ts": _iso_now(),
            })
            return

        tool_name = decision.get("tool", "NONE")
        tool_args = decision.get("args", {})
        model_used = decision.get("model_used", "unknown")

        logger.info("[%s] Step %d: plan_next_action → tool=%s (model=%s)", task_id, step + 1, tool_name, model_used)

        # If the planner says NONE or returns an unknown tool, we're done
        if tool_name == "NONE" or tool_name not in TOOL_REGISTRY:
            # Check if we have enough results to consider the task successful
            if "lookup_booking" in results:
                # At minimum we looked up the booking
                avail = results.get("check_availability", {})
                if avail.get("available") is False:
                    # Seats not available — task completed but couldn't reschedule
                    await emit({
                        "event": "task_completed",
                        "success": True,
                        "degraded": False,
                        "message": "No seats available for the requested date.",
                        "ts": _iso_now(),
                    })
                    return
            break

        # Skip tools that have already been completed
        if tool_name in results:
            logger.info("[%s] Tool %s already completed, asking planner again", task_id, tool_name)
            continue

        # Skip tools that have been escalated
        if tool_name in escalated_tools:
            logger.info("[%s] Tool %s already escalated, asking planner again", task_id, tool_name)
            continue

        # Resolve actual function arguments
        real_fn = TOOL_REGISTRY[tool_name]
        call_args = _resolve_args(tool_name, tool_args, parsed, results)

        # Execute through resilience core (Part 03)
        try:
            result = await execute_tool_call(tool_name, real_fn, **call_args)

            # Check for degraded data flag
            if result.get("_degraded"):
                degraded = True
                result_clean = {k: v for k, v in result.items() if k != "_degraded"}
                results[tool_name] = result_clean
            else:
                results[tool_name] = result

            logger.info("[%s] Tool %s succeeded: %s", task_id, tool_name, result)

        except EscalationError as e:
            logger.warning("[%s] Tool %s escalated: %s", task_id, tool_name, e)
            escalated_tools[tool_name] = str(e)
            degraded = True

            # If a critical tool is escalated, we can't proceed past it
            if tool_name in ("lookup_booking", "check_availability"):
                # Can't continue without booking data or availability
                await emit({
                    "event": "task_completed",
                    "success": False,
                    "degraded": True,
                    "escalated_tools": list(escalated_tools.keys()),
                    "ts": _iso_now(),
                })
                return

            # For payment/notification escalation, the task continues but is degraded
            # The planner will see the escalation and skip to the next viable step

        except ValueError as e:
            # Input validation error — log and treat as a non-recoverable step failure
            logger.error("[%s] Tool %s input error: %s", task_id, tool_name, e)
            escalated_tools[tool_name] = f"Input validation error: {e}"
            degraded = True

    # Task complete — determine success
    required_completed = "lookup_booking" in results
    all_completed = all(
        t in results or t in escalated_tools
        for t in PIPELINE_ORDER
    )

    success = required_completed and len(escalated_tools) == 0
    await emit({
        "event": "task_completed",
        "success": success,
        "degraded": degraded,
        "completed_tools": list(results.keys()),
        "escalated_tools": list(escalated_tools.keys()),
        "ts": _iso_now(),
    })

    logger.info(
        "[%s] Task finished — success=%s, degraded=%s, completed=%s, escalated=%s",
        task_id, success, degraded, list(results.keys()), list(escalated_tools.keys()),
    )


def _resolve_args(
    tool_name: str,
    model_args: dict,
    parsed: dict,
    results: dict,
) -> dict:
    """
    Build the actual keyword arguments for a tool call.
    Uses model-suggested args but fills in / overrides with known-good values
    from parsed request and previous results to ensure the call succeeds.
    """
    if tool_name == "lookup_booking":
        return {
            "booking_id": model_args.get("booking_id", parsed["booking_id"]),
        }

    elif tool_name == "check_availability":
        booking = results.get("lookup_booking", {})
        return {
            "new_date": model_args.get("new_date", parsed["new_date"]),
            "route": model_args.get("route", booking.get("route", "DEL-BOM")),
        }

    elif tool_name == "charge_fare_difference":
        avail = results.get("check_availability", {})
        price_delta = avail.get("price_delta", 0.0)
        amount = model_args.get("amount", price_delta)
        # Ensure amount is a number
        if isinstance(amount, str):
            try:
                amount = float(amount)
            except ValueError:
                amount = price_delta
        return {
            "amount": float(amount),
            "payment_token": model_args.get("payment_token", parsed["payment_token"]),
        }

    elif tool_name == "send_confirmation":
        booking = results.get("lookup_booking", {})
        avail = results.get("check_availability", {})
        passenger_name = booking.get("passenger_name", "Guest")

        # Determine email
        email = model_args.get("email") or parsed.get("email")
        if not email or "@" not in str(email):
            email = passenger_name.replace(" ", ".").lower() + "@example.com"

        # Build itinerary from collected results
        itinerary = model_args.get("itinerary", {})
        if not itinerary or not isinstance(itinerary, dict) or len(itinerary) < 2:
            itinerary = {
                "booking_id": booking.get("booking_id", parsed["booking_id"]),
                "passenger_name": passenger_name,
                "route": booking.get("route", "DEL-BOM"),
                "old_date": booking.get("date", "unknown"),
                "new_date": parsed["new_date"],
                "fare": booking.get("fare", 0) + avail.get("price_delta", 0),
            }
            # Add transaction info if payment was processed
            payment = results.get("charge_fare_difference")
            if payment:
                itinerary["transaction_id"] = payment.get("transaction_id")
                itinerary["amount_charged"] = payment.get("amount")

        return {
            "email": email,
            "itinerary": itinerary,
        }

    # Fallback: pass model args directly
    return model_args
