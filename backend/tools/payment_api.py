import asyncio
import random
import uuid

async def charge_fare_difference(amount: float, payment_token: str) -> dict:
    """
    Returns:
    {
        "charged": bool,
        "transaction_id": str,
        "amount": float
    }
    """
    if not isinstance(amount, (int, float)):
        raise ValueError("amount must be a number")
    if not isinstance(payment_token, str) or not payment_token.strip():
        raise ValueError("payment_token must be a non-empty string")
        
    # Simulate network latency (200ms - 500ms)
    await asyncio.sleep(random.uniform(0.2, 0.5))
    
    return {
        "charged": True,
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
        "amount": float(amount)
    }
