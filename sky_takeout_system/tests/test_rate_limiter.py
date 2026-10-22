import asyncio
import sys
import time
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import HTTPException
from app.core.rate_limiter import RedisSlidingWindowLimiter
from app.core.redis import get_redis_client, close_redis_client


async def run_rate_limiter_verification():
    """
    Automated Penetration & Concurrency Test for Redis Sliding Window Rate Limiter.
    Verifies:
      1. Rapid burst allowances up to max quota.
      2. Immediate 429 rejection on quota exhaustion with accurate Retry-After header.
      3. User isolation (user A being throttled must not affect user B).
      4. Auto-recovery after sliding window elapses.
    """
    print("=" * 70)
    print(" 🚀 STARTING REDIS SLIDING WINDOW RATE LIMITER VERIFICATION TEST")
    print("=" * 70)

    # Clean Redis connection check
    redis_client = get_redis_client()
    pong = await redis_client.ping()
    print(f"📡 Redis Ping Response: {pong} (Connected successfully)")

    # Configure a fast-testing rate limiter: 5 requests per 3-second window
    test_window_seconds = 3
    test_max_requests = 5
    limiter = RedisSlidingWindowLimiter(
        key_prefix="test:rate_limit:user",
        max_requests=test_max_requests,
        window_seconds=test_window_seconds,
    )

    user_alice = "USER_ALICE_BURST_001"
    user_bob = "USER_BOB_INDEPENDENT_002"

    # Reset test keys for clean test state
    await limiter.reset(user_alice)
    await limiter.reset(user_bob)

    # -------------------------------------------------------------------------
    # Test Case 1: Burst Quota Allowances (5 allowed requests)
    # -------------------------------------------------------------------------
    print("\n[Case 1]: Simulating rapid burst of 5 legitimate requests for Alice...")
    for i in range(1, test_max_requests + 1):
        allowed, remaining, retry_after = await limiter.is_allowed(user_alice)
        print(f"  👉 Request #{i}: allowed={allowed}, remaining={remaining}, retry_after={retry_after}s")
        assert allowed is True, f"Request #{i} should be allowed!"
        assert remaining == (test_max_requests - i), f"Remaining quota mismatch on request #{i}!"

    print("  ✅ [PASS] All 5 burst requests within quota were successfully granted!")

    # -------------------------------------------------------------------------
    # Test Case 2: 6th Request Exceeds Quota (Blocked with 429 & Retry-After)
    # -------------------------------------------------------------------------
    print("\n[Case 2]: Sending 6th burst request for Alice (Should exceed quota)...")
    allowed, remaining, retry_after = await limiter.is_allowed(user_alice)
    print(f"  🛑 Request #6: allowed={allowed}, remaining={remaining}, retry_after={retry_after}s")
    assert allowed is False, "Request #6 must be BLOCKED!"
    assert remaining == 0, "Remaining quota must be 0!"
    assert retry_after > 0, "Retry-After must be greater than 0!"
    print(f"  ✅ [PASS] Request #6 correctly blocked! Retry-After countdown: {retry_after} seconds.")

    # -------------------------------------------------------------------------
    # Test Case 3: Verify check_and_record raises HTTPException(429)
    # -------------------------------------------------------------------------
    print("\n[Case 3]: Testing check_and_record() exception handling...")
    try:
        await limiter.check_and_record(user_alice)
        assert False, "check_and_record() should have raised HTTPException(429)!"
    except HTTPException as exc:
        print(f"  🛡️ Intercepted HTTPException: Status={exc.status_code}")
        print(f"     Detail message: \"{exc.detail}\"")
        print(f"     Headers: {exc.headers}")
        assert exc.status_code == 429
        assert "Retry-After" in exc.headers
        print("  ✅ [PASS] HTTPException(429) correctly raised with proper Retry-After header!")

    # -------------------------------------------------------------------------
    # Test Case 4: User Isolation (Bob must NOT be throttled by Alice's burst)
    # -------------------------------------------------------------------------
    print("\n[Case 4]: Testing Multi-Tenant User Isolation (Bob's request)...")
    bob_allowed, bob_remaining, _ = await limiter.is_allowed(user_bob)
    print(f"  👤 Bob Request #1: allowed={bob_allowed}, remaining={bob_remaining}")
    assert bob_allowed is True, "Bob's quota must NOT be impacted by Alice's rate limit!"
    assert bob_remaining == (test_max_requests - 1)
    print("  ✅ [PASS] User isolation confirmed: Bob operates under an independent sliding window!")

    # -------------------------------------------------------------------------
    # Test Case 5: Sliding Window Recovery (Wait for window to elapse)
    # -------------------------------------------------------------------------
    wait_time = test_window_seconds + 0.5
    print(f"\n[Case 5]: Waiting {wait_time:.1f}s for Alice's sliding window to elapse...")
    await asyncio.sleep(wait_time)

    rec_allowed, rec_remaining, _ = await limiter.is_allowed(user_alice)
    print(f"  🔄 Alice Post-Window Request: allowed={rec_allowed}, remaining={rec_remaining}")
    assert rec_allowed is True, "Alice should be granted access once sliding window expires!"
    print("  ✅ [PASS] Sliding window smoothly recovered! Historical timestamps correctly expired.")

    # Cleanup test keys
    await limiter.reset(user_alice)
    await limiter.reset(user_bob)
    await close_redis_client()

    print("\n" + "=" * 70)
    print(" 🏆 ALL 5 RATE LIMITER TEST SUITES PASSED FLAWLESSLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_rate_limiter_verification())
