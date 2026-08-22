import asyncio
import time
from backend.tools.booking_api import lookup_booking
from backend.tools.availability_api import check_availability
from backend.tools.payment_api import charge_fare_difference
from backend.tools.notification_api import send_confirmation

async def run_tests():
    print("Testing lookup_booking (valid)...")
    t0 = time.time()
    booking = await lookup_booking("BKG123")
    t1 = time.time()
    print(f"Result: {booking}, Latency: {t1-t0:.3f}s")
    assert booking["booking_id"] == "BKG123"
    assert 0.2 <= (t1-t0) <= 0.6
    
    print("\nTesting check_availability (Success)...")
    t0 = time.time()
    avail = await check_availability("2026-09-02", "DEL-BOM")
    t1 = time.time()
    print(f"Result: {avail}, Latency: {t1-t0:.3f}s")
    assert avail["available"] == True
    assert 0.2 <= (t1-t0) <= 0.6
    
    print("\nTesting check_availability (Fail)...")
    t0 = time.time()
    avail_fail = await check_availability("2026-12-25", "DEL-BOM")
    t1 = time.time()
    print(f"Result: {avail_fail}, Latency: {t1-t0:.3f}s")
    assert avail_fail["available"] == False
    assert 0.2 <= (t1-t0) <= 0.6
    
    print("\nTesting charge_fare_difference...")
    t0 = time.time()
    charge = await charge_fare_difference(50.0, "tok_123")
    t1 = time.time()
    print(f"Result: {charge}, Latency: {t1-t0:.3f}s")
    assert charge["charged"] == True
    assert 0.2 <= (t1-t0) <= 0.6
    
    print("\nTesting send_confirmation...")
    t0 = time.time()
    notif = await send_confirmation("user@example.com", booking)
    t1 = time.time()
    print(f"Result: {notif}, Latency: {t1-t0:.3f}s")
    assert notif["sent"] == True
    assert 0.2 <= (t1-t0) <= 0.6
    
    print("\nTesting exceptions...")
    try:
        await lookup_booking("")
        assert False, "Should have raised ValueError for empty booking_id"
    except ValueError as e:
        print(f"Caught expected ValueError for lookup_booking: {e}")
        
    try:
        await check_availability("", "DEL-BOM")
        assert False, "Should have raised ValueError for empty date"
    except ValueError as e:
        print(f"Caught expected ValueError for check_availability: {e}")
        
    try:
        await charge_fare_difference("abc", "tok_123")
        assert False, "Should have raised ValueError for invalid amount type"
    except ValueError as e:
        print(f"Caught expected ValueError for charge_fare_difference: {e}")
        
    try:
        await send_confirmation("userexample.com", booking)
        assert False, "Should have raised ValueError for invalid email"
    except ValueError as e:
        print(f"Caught expected ValueError for send_confirmation: {e}")
        
    print("\nAll tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
