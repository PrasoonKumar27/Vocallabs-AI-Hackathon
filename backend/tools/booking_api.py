import asyncio
import random

# In-memory dict (seed with 3-5 fake bookings)
MOCK_BOOKINGS = {
    "BKG123": {
        "booking_id": "BKG123",
        "passenger_name": "Alice Smith",
        "route": "DEL-BOM",
        "date": "2026-09-01",
        "fare": 150.0
    },
    "BKG456": {
        "booking_id": "BKG456",
        "passenger_name": "Bob Jones",
        "route": "LHR-JFK",
        "date": "2026-09-05",
        "fare": 450.0
    },
    "BKG789": {
        "booking_id": "BKG789",
        "passenger_name": "Charlie Brown",
        "route": "SFO-ORD",
        "date": "2026-09-10",
        "fare": 200.0
    },
    "BKG999": {
        "booking_id": "BKG999",
        "passenger_name": "Diana Prince",
        "route": "CDG-DXB",
        "date": "2026-10-15",
        "fare": 600.0
    }
}

async def lookup_booking(booking_id: str) -> dict:
    """
    Returns:
    {
        "booking_id": str,
        "passenger_name": str,
        "route": str,          # e.g. "DEL-BOM"
        "date": str,           # ISO date, e.g. "2026-09-01"
        "fare": float
    }
    """
    if not isinstance(booking_id, str) or not booking_id.strip():
        raise ValueError("booking_id must be a non-empty string")
        
    # Simulate network latency (200ms - 500ms)
    await asyncio.sleep(random.uniform(0.2, 0.5))
    
    if booking_id not in MOCK_BOOKINGS:
        raise ValueError(f"Booking ID '{booking_id}' not found")
        
    return MOCK_BOOKINGS[booking_id].copy()
