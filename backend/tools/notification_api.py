import asyncio
import random
import uuid

async def send_confirmation(email: str, itinerary: dict) -> dict:
    """
    Returns:
    {
        "sent": bool,
        "message_id": str
    }
    """
    if not isinstance(email, str) or not email.strip() or "@" not in email:
        raise ValueError("email must be a valid non-empty string containing '@'")
    if not isinstance(itinerary, dict) or not itinerary:
        raise ValueError("itinerary must be a non-empty dictionary")
        
    # Simulate network latency (200ms - 500ms)
    await asyncio.sleep(random.uniform(0.2, 0.5))
    
    return {
        "sent": True,
        "message_id": f"msg_{uuid.uuid4().hex[:12]}"
    }
