# tests/integration/test_kernel_perf.py
"""
Performance Benchmarks for ExecutionKernel

Measures:
- Average latency per operation (target: <1ms)
- Operations per second
- Memory overhead
- Fast path vs. validation path performance

Based on docs/7.md recommendations.
"""

import pytest
import timeit
import tracemalloc
import statistics
from typing import Dict, Any, List
from datetime import datetime

from kernel.execution_kernel import ExecutionKernel, KernelConfig
from kernel.intent_contract import (
    IntentContract,
    RequirePermission,
    ProtectedPathCheck,
    ContractBuilder,
)
from kernel.invariants import combined_safety_invariant


# =============================================================================
# BENCHMARK FIXTURES
# =============================================================================

@pytest.fixture
def perf_kernel():
    """Create kernel for performance testing."""
    config = KernelConfig(
        environment="test",
        skip_manifest_validation=True,  # Skip for clean perf measurement
        enable_audit=False,  # Disable audit for perf testing
    )
    kernel = ExecutionKernel(config=config)

    # Register test operations
    kernel.register_operation(
        "fast_op",
        lambda **kwargs: {"result": "ok", "value": kwargs.get("value", 0)},
        "Fast operation"
    )

    kernel.register_operation(
        "compute_op",
        lambda x, y: x + y,
        "Compute operation"
    )

    kernel.register_operation(
        "io_op",
        lambda path: f"read: {path}",
        "IO operation simulation"
    )

    # Add invariants (adds overhead)
    kernel.add_invariant(combined_safety_invariant, "combined_safety")

    return kernel


@pytest.fixture
def kernel_with_contracts():
    """Create kernel with IntentContracts for testing."""
    config = KernelConfig(
        environment="test",
        skip_manifest_validation=True,
        enable_audit=False,
    )
    kernel = ExecutionKernel(config=config)

    # Register operation (accept **kwargs to handle permissions from contracts)
    kernel.register_operation(
        "protected_op",
        lambda **kwargs: f"processed: {kwargs.get('path', 'unknown')}",
        "Protected operation"
    )

    # Add contract
    contract = IntentContract("protected_contract", fail_fast=True)
    contract.add_pre_check(RequirePermission("op.execute"))
    contract.add_pre_check(ProtectedPathCheck())
    kernel.register_contract("protected_op", contract)

    return kernel


# =============================================================================
# BASELINE BENCHMARKS
# =============================================================================

class TestKernelPerf:
    """Performance benchmarks for ExecutionKernel."""

    def test_fast_op_latency_baseline(self, perf_kernel):
        """
        Baseline latency for fast operation.

        Target: <1ms per operation
        """
        # Warmup
        for _ in range(100):
            perf_kernel.execute("fast_op", {"value": 1}, "test_agent", {})

        # Measure
        iterations = 1000
        start = datetime.now()

        for _ in range(iterations):
            perf_kernel.execute("fast_op", {"value": 1}, "test_agent", {})

        elapsed = (datetime.now() - start).total_seconds()
        avg_ms = (elapsed / iterations) * 1000
        ops_per_sec = iterations / elapsed

        print(f"\n[BENCHMARK] Fast operation:")
        print(f"  Total time: {elapsed:.4f}s")
        print(f"  Avg latency: {avg_ms:.4f}ms")
        print(f"  Ops/sec: {ops_per_sec:.0f}")

        # Assert target <1ms
        assert avg_ms < 1.0, f"Latency too high: {avg_ms:.4f}ms (target: <1ms)"

        # Store for reporting
        self.fast_op_avg_ms = avg_ms
        self.ops_per_sec = ops_per_sec

    def test_compute_op_throughput(self, perf_kernel):
        """
        Throughput for compute operations.
        """
        iterations = 5000

        # Measure with timeit for accuracy
        def run_batch():
            for i in range(iterations):
                perf_kernel.execute("compute_op", {"x": i, "y": i+1}, "test_agent", {})

        elapsed = timeit.timeit(run_batch, number=1)
        avg_ms = (elapsed / iterations) * 1000
        ops_per_sec = iterations / elapsed

        print(f"\n[BENCHMARK] Compute throughput ({iterations} ops):")
        print(f"  Total time: {elapsed:.4f}s")
        print(f"  Avg latency: {avg_ms:.4f}ms")
        print(f"  Ops/sec: {ops_per_sec:.0f}")

        # Should be fast
        assert avg_ms < 5.0, f"Compute too slow: {avg_ms:.4f}ms"

    def test_memory_overhead(self, perf_kernel):
        """
        Memory overhead of kernel operations.

        Uses tracemalloc to measure peak memory.
        """
        tracemalloc.start()

        # Snapshot before
        snapshot_before = tracemalloc.take_snapshot()

        # Execute operations
        for i in range(1000):
            perf_kernel.execute("fast_op", {"value": i}, "test_agent", {})

        # Snapshot after
        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Calculate overhead
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        total_mb = sum(stat.size_diff for stat in top_stats) / (1024 * 1024)

        print(f"\n[BENCHMARK] Memory overhead:")
        print(f"  Total overhead: {total_mb:.2f}MB")
        print(f"  Per operation: {total_mb/1024:.4f}KB")

        # Should be reasonable (<100MB for 1000 ops)
        assert total_mb < 100, f"Memory overhead too high: {total_mb:.2f}MB"

    def test_contract_overhead(self, kernel_with_contracts):
        """
        Measure overhead of IntentContract validation.
        """
        # Compare with/without contract
        simple_kernel = ExecutionKernel(
            config=KernelConfig(skip_manifest_validation=True, enable_audit=False)
        )
        simple_kernel.register_operation(
            "op",
            lambda path: f"ok: {path}",
            "Simple op"
        )

        # Baseline (no contract)
        iterations = 500
        baseline_time = timeit.timeit(
            lambda: simple_kernel.execute("op", {"path": "/tmp/test"}, "agent", {}),
            number=iterations
        )

        # With contract
        contract_time = timeit.timeit(
            lambda: kernel_with_contracts.execute(
                "protected_op",
                {"path": "/tmp/test", "permissions": ["op.execute"]},
                "agent",
                {}
            ),
            number=iterations
        )

        baseline_avg_ms = (baseline_time / iterations) * 1000
        contract_avg_ms = (contract_time / iterations) * 1000
        overhead_ms = contract_avg_ms - baseline_avg_ms
        overhead_pct = (overhead_ms / baseline_avg_ms) * 100

        print(f"\n[BENCHMARK] Contract overhead:")
        print(f"  Baseline: {baseline_avg_ms:.4f}ms")
        print(f"  With contract: {contract_avg_ms:.4f}ms")
        print(f"  Overhead: {overhead_ms:.4f}ms ({overhead_pct:.1f}%)")

        # Contract overhead check: absolute overhead should be <0.1ms
        # Percentage can be high when baseline is very fast
        assert overhead_ms < 0.1, f"Contract absolute overhead too high: {overhead_ms:.4f}ms"
        # Also ensure percentage is reasonable (<500%)
        assert overhead_pct < 500, f"Contract percentage overhead too high: {overhead_pct:.1f}%"


# =============================================================================
# STRESS TESTS
# =============================================================================

class TestKernelStress:
    """Stress tests to find performance cliffs."""

    def test_rapid_operations(self, perf_kernel):
        """
        Rapid successive operations - check for bottlenecks.
        """
        timings = []
        iterations = 100

        for i in range(iterations):
            start = datetime.now()
            perf_kernel.execute("fast_op", {"value": i}, "test_agent", {})
            elapsed = (datetime.now() - start).total_seconds() * 1000
            timings.append(elapsed)

        avg = statistics.mean(timings)
        median = statistics.median(timings)
        p95 = statistics.quantiles(timings, n=20)[18]  # 95th percentile
        p99 = statistics.quantiles(timings, n=100)[98]  # 99th percentile

        print(f"\n[BENCHMARK] Rapid ops latency distribution:")
        print(f"  Mean: {avg:.4f}ms")
        print(f"  Median: {median:.4f}ms")
        print(f"  P95: {p95:.4f}ms")
        print(f"  P99: {p99:.4f}ms")

        # P99 should be <20ms (allowing occasional GC spikes)
        assert p99 < 20.0, f"P99 latency too high: {p99:.4f}ms"

    def test_concurrent_simulation(self, perf_kernel):
        """
        Simulate concurrent access (sequential but rapid).
        """
        agents = [f"agent_{i}" for i in range(10)]
        iterations_per_agent = 100

        start = datetime.now()

        for agent in agents:
            for i in range(iterations_per_agent):
                perf_kernel.execute("fast_op", {"value": i}, agent, {})

        elapsed = (datetime.now() - start).total_seconds()
        total_ops = len(agents) * iterations_per_agent
        avg_ms = (elapsed / total_ops) * 1000

        print(f"\n[BENCHMARK] Concurrent simulation ({len(agents)} agents):")
        print(f"  Total ops: {total_ops}")
        print(f"  Total time: {elapsed:.4f}s")
        print(f"  Avg latency: {avg_ms:.4f}ms")
        print(f"  Ops/sec: {total_ops/elapsed:.0f}")

        assert avg_ms < 2.0, f"Concurrent latency too high: {avg_ms:.4f}ms"


# =============================================================================
# SCALING TESTS
# =============================================================================

class TestKernelScaling:
    """Tests to check performance scaling."""

    def test_payload_size_impact(self, perf_kernel):
        """
        Measure latency impact of payload size.
        """
        sizes = [100, 1000, 10000, 100000]  # bytes
        results = {}

        for size in sizes:
            payload = {"data": "x" * size}
            iterations = max(10, 10000 // size)  # Fewer for large payloads

            elapsed = timeit.timeit(
                lambda: perf_kernel.execute("fast_op", payload, "test_agent", {}),
                number=iterations
            )

            avg_ms = (elapsed / iterations) * 1000
            results[size] = avg_ms

        print(f"\n[BENCHMARK] Payload size impact:")
        for size, latency in results.items():
            print(f"  {size:>6} bytes: {latency:.4f}ms")

        # Large payloads (100KB) should not be excessively slower than small (100B).
        # Threshold is generous (50x) to accommodate shared CI environments.
        ratio = results[100000] / results[100]
        assert ratio < 50, f"Large payload penalty too high: {ratio:.1f}x"

    def test_invariant_scaling(self, perf_kernel):
        """
        Measure overhead of multiple invariants.
        """
        # Create kernels with different invariant counts
        invariant_counts = [0, 1, 5, 10]
        results = {}

        for count in invariant_counts:
            kernel = ExecutionKernel(
                config=KernelConfig(skip_manifest_validation=True, enable_audit=False)
            )
            kernel.register_operation("op", lambda x: x, "Test op")

            # Add invariants
            for i in range(count):
                kernel.add_invariant(lambda p: True, f"invariant_{i}")

            # Measure
            iterations = 1000
            elapsed = timeit.timeit(
                lambda: kernel.execute("op", {"x": 1}, "agent", {}),
                number=iterations
            )

            avg_ms = (elapsed / iterations) * 1000
            results[count] = avg_ms

        print(f"\n[BENCHMARK] Invariant scaling:")
        for count, latency in results.items():
            print(f"  {count:>2} invariants: {latency:.4f}ms")

        # 10 invariants should not be 5x slower than 0
        ratio = results[10] / results[0] if results[0] > 0 else 1
        assert ratio < 5, f"Invariant scaling too high: {ratio:.1f}x"


# =============================================================================
# MEMORY LEAK DETECTION
# =============================================================================

class TestMemoryLeaks:
    """Tests for memory leak detection."""

    def test_no_leak_on_repeated_ops(self, perf_kernel):
        """
        Check for memory leaks on repeated operations.
        """
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        # Many operations
        for i in range(10000):
            perf_kernel.execute("fast_op", {"value": i}, "test_agent", {})

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Get top memory consumers
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        total_kb = sum(stat.size_diff for stat in top_stats) / 1024

        print(f"\n[BENCHMARK] Memory leak check:")
        print(f"  Memory growth: {total_kb:.2f}KB")
        print(f"  Per operation: {total_kb/10000:.4f}KB")

        # Growth should be minimal (<10KB per 1000 ops)
        assert total_kb < 100, f"Possible memory leak: {total_kb:.2f}KB growth"

    def test_contract_no_leak(self, kernel_with_contracts):
        """
        Check that contracts don't leak memory.
        """
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        for i in range(1000):
            kernel_with_contracts.execute(
                "protected_op",
                {"path": f"/tmp/test{i}", "permissions": ["op.execute"]},
                "agent",
                {}
            )

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        total_kb = sum(stat.size_diff for stat in snapshot_after.compare_to(snapshot_before, 'lineno')) / 1024

        print(f"\n[BENCHMARK] Contract memory check:")
        print(f"  Memory growth: {total_kb:.2f}KB")

        assert total_kb < 50, f"Contract memory leak: {total_kb:.2f}KB"


# =============================================================================
# COMPARATIVE BENCHMARKS
# =============================================================================

class TestComparativePerf:
    """Compare different execution paths."""

    def test_fast_vs_validated_path(self, perf_kernel):
        """
        Compare fast path (skip validation) vs validated path.
        """
        iterations = 1000

        # Fast path (skip_manifest_validation=True)
        fast_time = timeit.timeit(
            lambda: perf_kernel.execute("fast_op", {"value": 1}, "test_agent", {}),
            number=iterations
        )

        # Create kernel with full validation (but skip manifest check for clean comparison)
        full_kernel = ExecutionKernel(
            config=KernelConfig(skip_manifest_validation=True, enable_audit=False)
        )
        full_kernel.register_operation("op", lambda **kwargs: kwargs.get("v"), "Op")
        full_kernel.add_invariant(lambda p: True, "stub")

        full_time = timeit.timeit(
            lambda: full_kernel.execute("op", {"value": 1}, "test_agent", {}),
            number=iterations
        )

        fast_avg = (fast_time / iterations) * 1000
        full_avg = (full_time / iterations) * 1000
        overhead_pct = ((full_avg - fast_avg) / fast_avg) * 100

        print(f"\n[BENCHMARK] Path comparison:")
        print(f"  Fast path: {fast_avg:.4f}ms")
        print(f"  Full validation: {full_avg:.4f}ms")
        print(f"  Overhead: {overhead_pct:.1f}%")

        # Full validation should not be 10x slower
        assert overhead_pct < 1000, f"Validation overhead too high: {overhead_pct:.0f}%"


# =============================================================================
# PERFORMANCE REPORT
# =============================================================================

@pytest.mark.benchmark
class TestPerformanceReport:
    """Generate comprehensive performance report."""

    def test_full_performance_report(self, perf_kernel):
        """
        Generate full performance report.
        Run with: pytest -m benchmark -v -s
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "system": "ExecutionKernel",
            "results": {}
        }

        # 1. Baseline latency
        iterations = 1000
        start = datetime.now()
        for i in range(iterations):
            perf_kernel.execute("fast_op", {"value": i}, "test_agent", {})
        baseline_latency_ms = ((datetime.now() - start).total_seconds() / iterations) * 1000
        report["results"]["baseline_latency_ms"] = round(baseline_latency_ms, 4)

        # 2. Throughput
        report["results"]["ops_per_sec"] = round(1 / (baseline_latency_ms / 1000), 0)

        # 3. Memory baseline
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()
        for _ in range(100):
            perf_kernel.execute("fast_op", {"value": 1}, "test_agent", {})
        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()
        memory_kb = sum(stat.size_diff for stat in snapshot_after.compare_to(snapshot_before, 'lineno')) / 1024
        report["results"]["memory_per_100_ops_kb"] = round(memory_kb, 2)

        # 4. Status
        report["status"] = "PASS" if baseline_latency_ms < 1.0 else "FAIL"
        report["target_latency_ms"] = 1.0

        print("\n" + "="*60)
        print(" PERFORMANCE REPORT ")
        print("="*60)
        print(f"Timestamp: {report['timestamp']}")
        print(f"Status:    {report['status']}")
        print(f"")
        print(f"Baseline Latency:  {report['results']['baseline_latency_ms']:.4f}ms (target: <{report['target_latency_ms']}ms)")
        print(f"Throughput:        {report['results']['ops_per_sec']:.0f} ops/sec")
        print(f"Memory (100 ops):  {report['results']['memory_per_100_ops_kb']:.2f}KB")
        print("="*60)

        # Assert performance target
        assert baseline_latency_ms < 1.0, f"FAIL: Latency {baseline_latency_ms:.4f}ms exceeds target 1.0ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
