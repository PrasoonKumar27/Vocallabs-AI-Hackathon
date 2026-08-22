import asyncio
import random
from typing import Callable
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Shared Exceptions for specific routing in Core
class ServerError500(Exception):
    """Simulates a generic 500 Internal Server Error."""
    pass

class RateLimitError(Exception):
    """Simulates a 429 Too Many Requests."""
    pass

# Constants matching Part 00 spec
FAULT_TYPES = {"NONE", "ERROR_500", "CORRUPT_PAYLOAD", "LATENCY_SPIKE", "SILENT_NULL", "RATE_LIMIT"}
TOOL_NAMES = {"lookup_booking", "check_availability", "charge_fare_difference", "send_confirmation"}

# In-memory chaos configuration
chaos_config: dict[str, dict] = {
    "lookup_booking": {"fault": "NONE", "remaining": 0},
    "check_availability": {"fault": "NONE", "remaining": 0},
    "charge_fare_difference": {"fault": "NONE", "remaining": 0},
    "send_confirmation": {"fault": "NONE", "remaining": 0},
}

router = APIRouter()

class ChaosSetRequest(BaseModel):
    tool: str
    fault: str
    count: int

@router.post("/api/chaos/set")
async def set_chaos(request: ChaosSetRequest):
    if request.tool not in TOOL_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid tool: {request.tool}")
    if request.fault not in FAULT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid fault type: {request.fault}")
    if request.count < 0:
        raise HTTPException(status_code=400, detail="count must be >= 0")
        
    chaos_config[request.tool] = {"fault": request.fault, "remaining": request.count}
    return {"ok": True}

async def call_with_chaos(tool_name: str, real_fn: Callable, *args, **kwargs) -> dict:
    """
    Wraps a tool call to inject configured chaos.
    Checks chaos_config[tool_name]; if a fault is active and remaining > 0,
    applies that fault instead of / in addition to calling real_fn.
    Decrements `remaining`. Always returns a dict or raises.
    """
    if tool_name not in chaos_config:
        raise ValueError(f"Tool {tool_name} is not managed by chaos_middleware")
        
    config = chaos_config[tool_name]
    fault = config["fault"]
    
    if config["remaining"] > 0 and fault != "NONE":
        config["remaining"] -= 1
        
        # Snapshot the fault to execute, then reset if this was the last use
        if config["remaining"] == 0:
            config["fault"] = "NONE"
            
        if fault == "ERROR_500":
            raise ServerError500(f"Chaos injected: 500 Internal Server Error in {tool_name}")
            
        elif fault == "RATE_LIMIT":
            raise RateLimitError(f"Chaos injected: 429 Too Many Requests in {tool_name}")
            
        elif fault == "LATENCY_SPIKE":
            await asyncio.sleep(4.1)
            return await real_fn(*args, **kwargs)
            
        elif fault == "SILENT_NULL":
            # Returns empty dict (meaning data is missing)
            return {}
            
        elif fault == "CORRUPT_PAYLOAD":
            # Run the real function, then mangle the output
            result = await real_fn(*args, **kwargs)
            
            if isinstance(result, dict) and len(result) > 0:
                keys = list(result.keys())
                # Prefer corrupting a typed field (bool or number) for reliable detection
                typed_keys = [k for k in keys if isinstance(result[k], (bool, int, float))]
                key_to_corrupt = random.choice(typed_keys) if typed_keys else random.choice(keys)
                val = result[key_to_corrupt]
                
                # Always produce a TYPE mismatch so schema validation catches it
                if isinstance(val, bool):
                    result[key_to_corrupt] = "yes" if val else "no"
                elif isinstance(val, (int, float)):
                    result[key_to_corrupt] = str(val) + "_corrupted"
                elif isinstance(val, str):
                    result[key_to_corrupt] = 99999  # int where string expected
                else:
                    result[key_to_corrupt] = None
                    
            return result
            
    # Default behavior: No fault configured, or count reached 0 before this call.
    return await real_fn(*args, **kwargs)
