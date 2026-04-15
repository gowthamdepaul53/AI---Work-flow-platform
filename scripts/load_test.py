"""
load_test.py
------------
Simulates high-throughput load to validate 50K+ TPS claim.
Uses async HTTP (aiohttp) for concurrent request generation.

Run: python scripts/load_test.py --url http://localhost:8000 --rps 1000 --duration 30

For full 50K TPS test, run distributed across multiple nodes with K6 or Locust.
This script validates the API can handle burst traffic and measure latency.
"""

import asyncio
import argparse
import time
import json
import random
import statistics
import logging
from dataclasses import dataclass, field
from typing import List

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# Sample ticket payloads for realistic load simulation
SAMPLE_TICKETS = [
    {
        "ticket_id": "load-{i}",
        "customer_name": "Test User {i}",
        "ticket_text": "I haven't received my refund after 2 weeks for order #{i}. Please help.",
        "urgency": "HIGH",
    },
    {
        "ticket_id": "load-{i}",
        "customer_name": "Dev User {i}",
        "ticket_text": "Getting HTTP 429 errors on API calls. We're on Pro tier.",
        "urgency": "MEDIUM",
    },
    {
        "ticket_id": "load-{i}",
        "customer_name": "Acme Corp {i}",
        "ticket_text": "Need to export all ticket data for compliance audit this week.",
        "urgency": "LOW",
    },
]


@dataclass
class LoadTestResult:
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_s(self) -> float:
        return self.end_time - self.start_time

    @property
    def actual_rps(self) -> float:
        return self.total_requests / self.duration_s if self.duration_s > 0 else 0

    @property
    def success_rate(self) -> float:
        return (self.successful / self.total_requests * 100) if self.total_requests > 0 else 0

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0

    @property
    def p95_ms(self) -> float:
        if not self.latencies_ms:
            return 0
        sorted_l = sorted(self.latencies_ms)
        return sorted_l[int(len(sorted_l) * 0.95)]

    @property
    def p99_ms(self) -> float:
        if not self.latencies_ms:
            return 0
        sorted_l = sorted(self.latencies_ms)
        return sorted_l[int(len(sorted_l) * 0.99)]

    def print_summary(self):
        print("\n" + "=" * 60)
        print("  LOAD TEST RESULTS")
        print("=" * 60)
        print(f"  Duration:        {self.duration_s:.1f}s")
        print(f"  Total requests:  {self.total_requests:,}")
        print(f"  Successful:      {self.successful:,} ({self.success_rate:.1f}%)")
        print(f"  Failed:          {self.failed:,}")
        print(f"  Actual RPS:      {self.actual_rps:,.0f}")
        print(f"  Latency P50:     {self.p50_ms:.1f}ms")
        print(f"  Latency P95:     {self.p95_ms:.1f}ms")
        print(f"  Latency P99:     {self.p99_ms:.1f}ms")
        print("=" * 60)
        if self.success_rate >= 99.9 and self.p99_ms < 200:
            print("  ✅ PASS — meets SLA (99.9% success, P99 < 200ms)")
        else:
            print("  ❌ FAIL — SLA not met")
        print("=" * 60 + "\n")


async def send_request(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict,
    result: LoadTestResult,
    semaphore: asyncio.Semaphore,
):
    async with semaphore:
        start = time.perf_counter()
        try:
            async with session.post(
                f"{url}/api/v1/workflow/support-ticket",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                await resp.json()
                elapsed_ms = (time.perf_counter() - start) * 1000
                result.total_requests += 1

                if resp.status == 200:
                    result.successful += 1
                    result.latencies_ms.append(elapsed_ms)
                else:
                    result.failed += 1
                    logger.debug(f"Non-200 response: {resp.status}")

        except asyncio.TimeoutError:
            result.total_requests += 1
            result.failed += 1
            logger.debug("Request timed out")
        except Exception as e:
            result.total_requests += 1
            result.failed += 1
            logger.debug(f"Request error: {e}")


async def run_load_test(url: str, target_rps: int, duration_s: int) -> LoadTestResult:
    """
    Generates `target_rps` requests per second for `duration_s` seconds.
    Uses a semaphore to cap concurrency and avoid overwhelming the client.
    """
    result = LoadTestResult()
    # Max concurrent requests: 10x RPS (assumes <100ms avg latency)
    semaphore = asyncio.Semaphore(target_rps * 10)

    connector = aiohttp.TCPConnector(limit=target_rps * 10, limit_per_host=target_rps * 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        logger.info(f"Starting load test: {target_rps} RPS for {duration_s}s → {url}")
        result.start_time = time.time()
        tasks = []

        interval = 1.0 / target_rps   # seconds between requests
        end_time = result.start_time + duration_s
        i = 0

        while time.time() < end_time:
            payload = dict(random.choice(SAMPLE_TICKETS))
            payload["ticket_id"] = f"load-{i}"
            payload["customer_name"] = f"Test User {i}"

            task = asyncio.create_task(
                send_request(session, url, payload, result, semaphore)
            )
            tasks.append(task)
            i += 1

            # Progress log every 5 seconds
            elapsed = time.time() - result.start_time
            if i % (target_rps * 5) == 0:
                logger.info(
                    f"  Progress: {elapsed:.0f}s | "
                    f"Sent: {result.total_requests:,} | "
                    f"RPS: {result.actual_rps:,.0f}"
                )

            await asyncio.sleep(interval)

        await asyncio.gather(*tasks, return_exceptions=True)
        result.end_time = time.time()

    return result


def main():
    parser = argparse.ArgumentParser(description="AI Platform Load Test")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--rps", type=int, default=100, help="Target requests per second")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds")
    args = parser.parse_args()

    result = asyncio.run(run_load_test(args.url, args.rps, args.duration))
    result.print_summary()

    # Exit with non-zero if SLA not met
    if result.success_rate < 99.9 or result.p99_ms > 200:
        exit(1)


if __name__ == "__main__":
    main()
