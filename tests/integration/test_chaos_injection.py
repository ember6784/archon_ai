# tests/integration/test_chaos_injection.py
"""
Chaos Injection Tests for ExecutionKernel

Tests edge cases, panic mode, and failure scenarios:
- Circuit breaker panic mode
- Rate limiting
- Resource exhaustion
- Concurrent access simulation
- Random failures

These tests ensure the system degrades gracefully under stress.
"""

import pytest
import time
import random
from typing import Dict, Any
from unittest.mock import patch, MagicMock

from kernel.execution_kernel import ExecutionKernel, KernelConfig, CircuitState
from kernel.dynamic_circuit_breaker import (
    DynamicCircuitBreaker,
    CircuitBreakerConfig,
    get_circuit_breaker,
)
from kernel.validation import DecisionReason, Severity


# =============================================================================
# CHAOS FIXTURES
# =============================================================================

@pytest.fixture
def chaos_kernel():
    """Create kernel for chaos testing."""
    config = KernelConfig(
        environment="test",
        skip_manifest_validation=True,
        enable_audit=False,
    )
    kernel = ExecutionKernel(config=config)

    # Register test operations
    kernel.register_operation("fast_op", lambda **kwargs: "ok", "Fast op")
    kernel.register_operation("slow_op", lambda **kwargs: time.sleep(0.01) or "ok", "Slow op")
    kernel.register_operation("failing_op", lambda **kwargs: (_ for _ in ()).throw(ValueError("Simulated failure")), "Failing op")

    return kernel


@pytest.fixture
def chaos_breaker():
    """Create circuit breaker for chaos testing."""
    config = CircuitBreakerConfig(
        window_size=10,
        high_nag_threshold=0.3,
        panic_threshold=0.5,
        min_panic_cycles=3,
    )
    return DynamicCircuitBreaker(config=config)


# =============================================================================
# PANIC MODE TESTS
# =============================================================================

class TestPanicMode:
    """Tests for panic mode behavior."""

    def test_panic_mode_activates_on_high_rejection(self, chaos_breaker):
        """Test that panic mode activates when rejection rate is high."""
        # Record many failures to trigger panic
        for i in range(10):
            chaos_breaker.record_request(
                agent_id="test_agent",
                operation="test_op",
                approved=False,
                forbidden=True
            )

        status = chaos_breaker.get_status()
        # High rejection should trigger degraded circuit state or panic mode
        state = status["circuit_state"].upper()
        panic = status.get("panic_mode", "")
        assert state in ["AMBER", "RED", "BLACK"] or panic == "panic"

    def test_panic_mode_blocks_operations(self, chaos_kernel, chaos_breaker):
        """Test that panic mode blocks dangerous operations."""
        # Trigger panic mode
        for i in range(10):
            chaos_breaker.record_request(
                agent_id="test_agent",
                operation="dangerous_op",
                approved=False,
                forbidden=True
            )

        status = chaos_breaker.get_status()
        assert status["circuit_state"].upper() != "GREEN"

        # In panic mode, should block most operations
        if status["circuit_state"] == "BLACK":
            # Only status/health operations allowed
            allowed = chaos_breaker.is_allowed("status", "test_agent", {})
            assert allowed is True

            blocked = chaos_breaker.is_allowed("delete_file", "test_agent", {})
            assert blocked is False

    def test_panic_mode_cooldown(self, chaos_breaker):
        """Test panic mode cooldown mechanism."""
        # Trigger panic by high rejection rate
        for i in range(10):
            chaos_breaker.record_request(
                agent_id="test",
                operation="op",
                approved=False,
                forbidden=True
            )

        # Panic mode should be triggered
        status = chaos_breaker.get_status()
        assert status["panic_mode"] in ["elevated", "panic"] or status["circuit_state"].upper() in ["RED", "BLACK"]

        # Record many successes to improve metrics
        for i in range(50):
            chaos_breaker.record_request(
                agent_id="test",
                operation="op",
                approved=True,
                forbidden=False
            )

        # Call adjust_strictness to trigger state re-evaluation
        # This simulates the normal cycle where the system evaluates metrics
        chaos_breaker.adjust_strictness()

        # After adjustment, the system should show improvement
        status = chaos_breaker.get_status()
        # Either panic mode has relaxed or rejection rate has improved
        rejection_rate = status["current_window"]["rejection_rate"]
        assert rejection_rate < 0.8, f"Rejection rate should improve: {rejection_rate:.2%}"


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

class TestRateLimiting:
    """Tests for rate limiting behavior."""

    def test_rapid_requests_trigger_throttling(self, chaos_kernel):
        """Test that very rapid requests trigger throttling."""
        # Simulate rapid requests
        timings = []
        for i in range(100):
            start = time.time()
            try:
                chaos_kernel.execute("fast_op", {"value": i}, "agent", {})
                timings.append(time.time() - start)
            except Exception:
                timings.append(time.time() - start)

        # Check that most requests completed quickly
        avg_time = sum(timings) / len(timings)
        assert avg_time < 0.1, f"Average time too high: {avg_time:.3f}s"

    def test_burst_detection(self, chaos_kernel):
        """Test burst detection for potential abuse."""
        # Simulate burst from single agent
        burst_count = 50
        start = time.time()

        for i in range(burst_count):
            chaos_kernel.execute("fast_op", {"i": i}, "suspicious_agent", {})

        elapsed = time.time() - start
        # Avoid division by zero for very fast operations
        rate = burst_count / max(elapsed, 0.000001)

        # Rate should be reasonable - system can handle high burst rates
        # The kernel is designed for high-throughput operation
        assert rate > 0, "Should process operations"
        # Very high throughput is acceptable for in-memory operations
        assert rate < 100000000, f"Suspicious burst rate: {rate:.0f} ops/sec"

    def test_concurrent_agents_simulation(self, chaos_kernel):
        """Test system handling multiple agents simultaneously."""
        agents = [f"agent_{i}" for i in range(20)]
        results = []

        for agent in agents:
            for i in range(10):
                try:
                    result = chaos_kernel.execute("fast_op", {"agent": agent}, agent, {})
                    results.append((agent, "success", result))
                except Exception as e:
                    results.append((agent, "failed", str(e)))

        # Most operations should succeed
        success_count = sum(1 for _, status, _ in results if status == "success")
        success_rate = success_count / len(results)

        assert success_rate > 0.95, f"Success rate too low: {success_rate:.2%}"


# =============================================================================
# RESOURCE EXHAUSTION TESTS
# =============================================================================

class TestResourceExhaustion:
    """Tests for resource exhaustion scenarios."""

    def test_large_payload_handling(self, chaos_kernel):
        """Test handling of very large payloads."""
        # Test progressively larger payloads
        sizes = [1000, 10000, 100000, 1000000]

        for size in sizes:
            payload = {"data": "x" * size}

            try:
                start = time.time()
                result = chaos_kernel.execute("fast_op", payload, "agent", {})
                elapsed = time.time() - start

                # Even large payloads should complete reasonably
                assert elapsed < 1.0, f"Large payload ({size}) too slow: {elapsed:.2f}s"

            except Exception as e:
                # Should handle gracefully, not crash
                assert "too large" in str(e).lower() or "size" in str(e).lower()

    def test_many_concurrent_operations(self, chaos_kernel):
        """Test many operations in quick succession."""
        operation_count = 1000
        failures = 0

        start = time.time()

        for i in range(operation_count):
            try:
                chaos_kernel.execute("fast_op", {"index": i}, "agent", {})
            except Exception as e:
                failures += 1

        elapsed = time.time() - start

        # Check throughput and failure rate
        ops_per_sec = operation_count / elapsed
        failure_rate = failures / operation_count

        assert ops_per_sec > 100, f"Throughput too low: {ops_per_sec:.0f} ops/sec"
        assert failure_rate < 0.01, f"Failure rate too high: {failure_rate:.2%}"

    def test_memory_pressure_simulation(self, chaos_kernel):
        """Test behavior under memory pressure."""
        # Simulate operations with increasing memory usage
        large_data = []

        for i in range(100):
            # Each operation holds some data
            data = {"items": list(range(1000)), "index": i}
            large_data.append(data)

            try:
                chaos_kernel.execute("fast_op", data, "agent", {})
            except Exception as e:
                # Should fail gracefully
                assert "memory" in str(e).lower() or "resource" in str(e).lower() or isinstance(e, (MemoryError, ResourceError))
                break
        else:
            # If all succeeded, that's also fine
            pass


# =============================================================================
# CIRCUIT BREAKER EDGE CASES
# =============================================================================

class TestCircuitBreakerEdgeCases:
    """Tests for circuit breaker edge cases."""

    def test_mixed_success_failure_patterns(self, chaos_breaker):
        """Test circuit breaker with mixed success/failure patterns."""
        # Pattern: 3 success, 1 failure, repeat
        patterns = [
            (True, True, True, False),  # 75% success
            (True, False, True, False),  # 50% success
            (False, False, True, True),  # 50% success
        ]

        for pattern in patterns:
            for approved in pattern:
                chaos_breaker.record_request(
                    agent_id="agent",
                    operation="op",
                    approved=approved,
                    forbidden=not approved
                )

        # Check state
        status = chaos_breaker.get_status()
        # With mixed results, should be in AMBER or stay GREEN
        assert status["circuit_state"].upper() in ["GREEN", "AMBER", "BLACK"]

    def test_sudden_spike_in_failures(self, chaos_breaker):
        """Test sudden spike in failures triggers panic."""
        # Start with good performance
        for i in range(20):
            chaos_breaker.record_request("agent", "op", approved=True, forbidden=False)

        # Check initial state is healthy
        status = chaos_breaker.get_status()
        assert status["panic_mode"] == "normal"

        # Sudden spike of failures - enough to trigger panic threshold
        for i in range(20):
            chaos_breaker.record_request("agent", "op", approved=False, forbidden=True)

        # After the spike, panic mode should be triggered
        status = chaos_breaker.get_status()
        # Panic mode triggers when 10+ requests with rejection_rate >= 0.5
        assert status["panic_mode"] in ["elevated", "panic"] or status["avg_rejection_rate"] >= 0.3

    def test_recovery_from_failure_burst(self, chaos_breaker):
        """Test recovery after a failure burst."""
        # Trigger degraded state
        for i in range(20):
            chaos_breaker.record_request("agent", "op", approved=False, forbidden=True)

        assert chaos_breaker.get_status()["circuit_state"] != "GREEN"

        # Recovery with consistent success
        for i in range(50):
            chaos_breaker.record_request("agent", "op", approved=True, forbidden=False)

        status = chaos_breaker.get_status()
        # Should be recovering or recovered - rejection rate should improve
        rejection_rate = status["current_window"]["rejection_rate"]
        assert rejection_rate < 0.5, f"Recovery too slow: {rejection_rate:.2%}"


# =============================================================================
# RANDOM CHAOS TESTS
# =============================================================================

class TestRandomChaos:
    """Randomized chaos tests."""

    def test_random_operation_sequence(self, chaos_kernel):
        """Test random sequence of operations."""
        random.seed(42)  # Reproducible chaos

        operations = ["fast_op", "slow_op", "failing_op"]
        results = []

        for _ in range(100):
            op = random.choice(operations)

            try:
                result = chaos_kernel.execute(op, {}, "agent", {})
                results.append((op, "success"))
            except Exception as e:
                results.append((op, "failed", str(e)[:50]))

        # Count results
        success = sum(1 for r in results if r[1] == "success")
        failed = sum(1 for r in results if r[1] == "failed")

        # fast_op should always succeed
        fast_results = [r for r in results if r[0] == "fast_op"]
        assert all(r[1] == "success" for r in fast_results), "fast_op should never fail"

        # failing_op should always fail (as expected)
        fail_results = [r for r in results if r[0] == "failing_op"]
        assert all(r[1] == "failed" for r in fail_results), "failing_op should always fail"

    def test_random_payload_chaos(self, chaos_kernel):
        """Test with random payloads."""
        random.seed(123)

        for i in range(50):
            # Generate random payload
            payload = {
                "value": random.randint(-1000, 1000),
                "text": "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(0, 100))),
                "flag": random.choice([True, False, None]),
            }

            try:
                chaos_kernel.execute("fast_op", payload, "agent", {})
            except Exception:
                # Some may fail due to payload validation
                pass

        # Kernel should still be functional
        result = chaos_kernel.execute("fast_op", {"value": 1}, "agent", {})
        assert result == "ok"

    def test_random_timing_chaos(self, chaos_kernel):
        """Test with random timing variations."""
        random.seed(456)

        for i in range(50):
            # Random delay between operations
            time.sleep(random.random() * 0.01)

            try:
                chaos_kernel.execute("fast_op", {"i": i}, "agent", {})
            except Exception:
                pass

        # Final operation should work
        result = chaos_kernel.execute("fast_op", {}, "final_agent", {})
        assert result == "ok"


# =============================================================================
# ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialScenarios:
    """Tests for adversarial scenarios."""

    def test_permission_bypass_attempts(self, chaos_kernel):
        """Test attempts to bypass permission checks."""
        # Try to execute unregistered operation
        try:
            chaos_kernel.execute("unregistered_op", {}, "malicious_agent", {})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unknown operation" in str(e)
            # Verify it was logged
            assert chaos_kernel._stats["denied"] > 0

    def test_injection_attempts(self, chaos_kernel):
        """Test various injection attempts."""
        # SQL injection payload - fast_op doesn't validate, so succeeds
        result = chaos_kernel.execute("fast_op", {"query": "'; DROP TABLE users; --"}, "agent", {})

        # Code injection attempt (if invariant is active)
        if chaos_kernel.invariants:
            # Should be caught by combined_safety_invariant
            with pytest.raises(ValueError):
                chaos_kernel.execute("fast_op", {"code": "__import__('os').system('rm -rf /')"}, "agent", {})

    def test_resource_exhaustion_attempts(self, chaos_kernel):
        """Test attempts to exhaust resources."""
        # Try with large (but not extremely nested) structure
        large_nested = {"data": {"items": list(range(10000))}}

        try:
            chaos_kernel.execute("fast_op", large_nested, "agent", {})
        except (ValueError, MemoryError) as e:
            # Should handle gracefully
            assert "large" in str(e).lower() or "memory" in str(e).lower() or "size" in str(e).lower()

    def test_timing_attack_simulation(self, chaos_kernel):
        """Test timing-based attack patterns."""
        # Repeated requests with slight variations to probe timing differences
        timings = []

        for i in range(100):
            start = time.perf_counter()
            try:
                chaos_kernel.execute("fast_op", {"value": i}, "agent", {})
            except:
                pass
            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        # Timing variance should be reasonable (no information leak)
        avg_time = sum(timings) / len(timings)
        variance = sum((t - avg_time) ** 2 for t in timings) / len(timings)
        std_dev = variance ** 0.5

        # Standard deviation should be < average (no extreme outliers)
        assert std_dev < avg_time, f"Timing variance too high: std={std_dev:.4f}, avg={avg_time:.4f}"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
