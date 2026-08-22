import asyncio
import random

async def check_availability(new_date: str, route: str) -> dict:
    """
    Returns:
    {
        "available": bool,
        "seats_left": int,
        "price_delta": float   # positive = new date costs more, negative = cheaper
    }
    """
    if not isinstance(new_date, str) or not new_date.strip():
        raise ValueError("new_date must be a non-empty string")
    if not isinstance(route, str) or not route.strip():
        raise ValueError("route must be a non-empty string")
        
    # Simulate network latency (200ms - 500ms)
    await asyncio.sleep(random.uniform(0.2, 0.5))
    
    # Deterministic test case where available is False (for branching logic)
    if route == "DEL-BOM" and new_date == "2026-12-25":
        return {
            "available": False,
            "seats_left": 0,
            "price_delta": 0.0
        }
        
    # Default success case
    return {
        "available": True,
        "seats_left": random.randint(1, 50),
        "price_delta": 117.91
    }
