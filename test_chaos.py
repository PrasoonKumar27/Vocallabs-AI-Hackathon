import asyncio
import time
from backend.chaos_middleware import call_with_chaos, chaos_config, set_chaos, ChaosSetRequest
from backend.chaos_middleware import ServerError500, RateLimitError
from backend.tools.payment_api import charge_fare_difference

async def run_tests():
    print("Testing Normal Execution...")
    res = await call_with_chaos("charge_fare_difference", charge_fare_difference, 50.0, "tok_1")
    print(f"Normal Result: {res}")
    assert res.get("charged") is True

    print("\nTesting ERROR_500...")
    await set_chaos(ChaosSetRequest(tool="charge_fare_difference", fault="ERROR_500", count=2))
    
    try:
        await call_with_chaos("charge_fare_difference", charge_fare_difference, 50.0, "tok_2")
        assert False, "Should have raised ServerError500"
    except ServerError500:
        print("Caught first ServerError500")
        
    try:
        await call_with_chaos("charge_fare_difference", charge_fare_difference, 50.0, "tok_3")
        assert False, "Should have raised ServerError500"
    except ServerError500:
        print("Caught second ServerError500")
        
    # Third time should succeed (count expired)
    res = await call_with_chaos("charge_fare_difference", charge_fare_difference, 50.0, "tok_4")
    print(f"Normal Result (after fault expired): {res}")
    assert res.get("charged") is True
    assert chaos_config["charge_fare_difference"]["fault"] == "NONE"

    print("\nTesting RATE_LIMIT...")
    await set_chaos(ChaosSetRequest(tool="charge_fare_difference", fault="RATE_LIMIT", count=1))
    try:
        await call_with_chaos("charge_fare_difference", charge_fare_difference, 50.0, "tok_5")
        assert False, "Should have raised RateLimitError"
    except RateLimitError:
        print("Caught RateLimitError")

    print("\nTesting SILENT_NULL...")
    await set_chaos(ChaosSetRequest(tool="charge_fare_difference", fault="SILENT_NULL", count=1))
    res = await call_with_chaos("charge_fare_difference", charge_fare_difference, 50.0, "tok_6")
    print(f"Silent Null Result: {res}")
    assert res == {}

    print("\nTesting CORRUPT_PAYLOAD...")
    await set_chaos(ChaosSetRequest(tool="charge_fare_difference", fault="CORRUPT_PAYLOAD", count=1))
    res = await call_with_chaos("charge_fare_difference", charge_fare_difference, 50.0, "tok_7")
    print(f"Corrupt Payload Result: {res}")
    # It should look different than the pure dictionary structure, e.g., 'charged': 'yes'
    assert res.get("charged") == "yes" or isinstance(res.get("amount"), str) or isinstance(res.get("transaction_id"), str)

    print("\nTesting LATENCY_SPIKE...")
    await set_chaos(ChaosSetRequest(tool="charge_fare_difference", fault="LATENCY_SPIKE", count=1))
    t0 = time.time()
    # We will wrap it with a timeout to avoid waiting too long during testing, but wait, the script actually sleeps 5-15 seconds.
    res = await call_with_chaos("charge_fare_difference", charge_fare_difference, 50.0, "tok_8")
    t1 = time.time()
    print(f"Latency Spike Result: {res}, Time Taken: {t1-t0:.2f}s")
    assert (t1 - t0) >= 5.0

    print("\nAll tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
