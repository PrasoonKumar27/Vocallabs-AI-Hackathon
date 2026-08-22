"""
Part 06 — Eval Harness Scenarios

Defines the test suite of chaos cases that the whole system must pass.
Includes every fault type across all tools.
"""

SCENARIOS = [
    # 1. ERROR_500
    {"id": "s01", "tool": "lookup_booking", "fault": "ERROR_500", "count": 1, "expect": "RECOVER"},
    {"id": "s02", "tool": "check_availability", "fault": "ERROR_500", "count": 1, "expect": "RECOVER"},
    {"id": "s03", "tool": "charge_fare_difference", "fault": "ERROR_500", "count": 1, "expect": "RECOVER"},
    {"id": "s04", "tool": "send_confirmation", "fault": "ERROR_500", "count": 1, "expect": "RECOVER"},

    # 2. RATE_LIMIT
    {"id": "s05", "tool": "lookup_booking", "fault": "RATE_LIMIT", "count": 1, "expect": "RECOVER"},
    {"id": "s06", "tool": "check_availability", "fault": "RATE_LIMIT", "count": 1, "expect": "RECOVER"},
    {"id": "s07", "tool": "charge_fare_difference", "fault": "RATE_LIMIT", "count": 1, "expect": "RECOVER"},
    {"id": "s08", "tool": "send_confirmation", "fault": "RATE_LIMIT", "count": 1, "expect": "RECOVER"},

    # 3. SILENT_NULL
    {"id": "s09", "tool": "lookup_booking", "fault": "SILENT_NULL", "count": 1, "expect": "RECOVER"},
    {"id": "s10", "tool": "check_availability", "fault": "SILENT_NULL", "count": 1, "expect": "RECOVER"},
    {"id": "s11", "tool": "charge_fare_difference", "fault": "SILENT_NULL", "count": 1, "expect": "RECOVER"},
    {"id": "s12", "tool": "send_confirmation", "fault": "SILENT_NULL", "count": 1, "expect": "RECOVER"},

    # 4. CORRUPT_PAYLOAD
    {"id": "s13", "tool": "lookup_booking", "fault": "CORRUPT_PAYLOAD", "count": 1, "expect": "RECOVER"},
    {"id": "s14", "tool": "check_availability", "fault": "CORRUPT_PAYLOAD", "count": 1, "expect": "RECOVER"},
    {"id": "s15", "tool": "charge_fare_difference", "fault": "CORRUPT_PAYLOAD", "count": 1, "expect": "RECOVER"},
    {"id": "s16", "tool": "send_confirmation", "fault": "CORRUPT_PAYLOAD", "count": 1, "expect": "RECOVER"},

    # 5. LATENCY_SPIKE
    {"id": "s17", "tool": "lookup_booking", "fault": "LATENCY_SPIKE", "count": 1, "expect": "RECOVER_SLOW"},
    {"id": "s18", "tool": "check_availability", "fault": "LATENCY_SPIKE", "count": 1, "expect": "RECOVER_SLOW"},
    {"id": "s19", "tool": "charge_fare_difference", "fault": "LATENCY_SPIKE", "count": 1, "expect": "RECOVER_SLOW"},
    {"id": "s20", "tool": "send_confirmation", "fault": "LATENCY_SPIKE", "count": 1, "expect": "RECOVER_SLOW"},

    # 6. ESCALATION (Payment Safety Net = 2 failures)
    {"id": "s21", "tool": "charge_fare_difference", "fault": "ERROR_500", "count": 2, "expect": "ESCALATE"},
    
    # 7. ESCALATION (Exhaust Retries = 3 failures for ERROR_500)
    {"id": "s22", "tool": "lookup_booking", "fault": "ERROR_500", "count": 3, "expect": "ESCALATE"},
]
