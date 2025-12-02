# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2025, Alan Dragomirecký

# This file is part of aiodbus, a fork of python-sdbus.

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
"""
Test for nested D-Bus calls across separate processes.

This test reproduces issues where nested D-Bus calls (A -> B -> C) cause
failures under stress:
- "Task was destroyed but it is pending!" warnings
- GeneratorExit thrown to async code unexpectedly
- Event loop collapse/strange async behavior

Architecture:
    Process A (Test) -> Process B (ServiceB) -> Process C (ServiceC)
    Each process waits for response from the next one in the chain.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import textwrap
import warnings
from pathlib import Path
from typing import List

from aiodbus import DbusInterfaceCommon, dbus_method
from aiodbus.unittest import IsolatedDbusTestCase

# Path to src directory for subprocess imports
SRC_PATH = str(Path(__file__).parent.parent / "src")

# Service names
SERVICE_B_NAME = "org.test.nested.ServiceB"
SERVICE_C_NAME = "org.test.nested.ServiceC"


class ServiceCInterface(
    DbusInterfaceCommon,
    interface_name="org.test.nested.ServiceC",
):
    """Terminal service that performs computation."""

    @dbus_method()
    async def compute(self, n: int, payload: str) -> str:
        """Simulate variable computation time and return result."""
        import random

        await asyncio.sleep(random.uniform(0.001, 0.01))
        return f"C:{n}:{len(payload)}"

    @dbus_method()
    async def ping(self) -> str:
        """Health check method."""
        return "pong"


class ServiceBInterface(
    DbusInterfaceCommon,
    interface_name="org.test.nested.ServiceB",
):
    """Middle service that forwards calls to ServiceC."""

    @dbus_method()
    async def call_c(self, n: int, payload: str) -> str:
        """Forward call to ServiceC and return combined result."""
        proxy_c = ServiceCInterface.new_proxy(SERVICE_C_NAME, "/")
        result_c = await proxy_c.compute(n, payload)
        return f"B:{n}:{result_c}"

    @dbus_method()
    async def ping(self) -> str:
        """Health check method."""
        return "pong"


# Worker script for ServiceC (terminal service)
SERVICE_C_SCRIPT = textwrap.dedent(
    f'''
    import asyncio
    import random
    import sys
    sys.path.insert(0, "{SRC_PATH}")

    from aiodbus import DbusInterfaceCommon, dbus_method, connect, set_default_bus

    class ServiceCInterface(
        DbusInterfaceCommon,
        interface_name="org.test.nested.ServiceC",
    ):
        @dbus_method()
        async def compute(self, n: int, payload: str) -> str:
            await asyncio.sleep(random.uniform(0.001, 0.01))
            return f"C:{{n}}:{{len(payload)}}"

        @dbus_method()
        async def ping(self) -> str:
            return "pong"

    async def main():
        bus = connect("session")
        set_default_bus(bus)

        await bus.request_name("{SERVICE_C_NAME}")

        service = ServiceCInterface()
        service.export_to_dbus("/")

        print("READY", flush=True)

        # Run forever
        while True:
            await asyncio.sleep(3600)

    if __name__ == "__main__":
        asyncio.run(main())
    '''
)

# Worker script for ServiceB (middle service that calls ServiceC)
SERVICE_B_SCRIPT = textwrap.dedent(
    f'''
    import asyncio
    import sys
    sys.path.insert(0, "{SRC_PATH}")

    from aiodbus import DbusInterfaceCommon, dbus_method, connect, set_default_bus

    SERVICE_C_NAME = "{SERVICE_C_NAME}"

    class ServiceCInterface(
        DbusInterfaceCommon,
        interface_name="org.test.nested.ServiceC",
    ):
        @dbus_method()
        async def compute(self, n: int, payload: str) -> str:
            ...

        @dbus_method()
        async def ping(self) -> str:
            ...

    class ServiceBInterface(
        DbusInterfaceCommon,
        interface_name="org.test.nested.ServiceB",
    ):
        @dbus_method()
        async def call_c(self, n: int, payload: str) -> str:
            proxy_c = ServiceCInterface.new_proxy(SERVICE_C_NAME, "/")
            result_c = await proxy_c.compute(n, payload)
            return f"B:{{n}}:{{result_c}}"

        @dbus_method()
        async def ping(self) -> str:
            return "pong"

    async def main():
        bus = connect("session")
        set_default_bus(bus)

        await bus.request_name("{SERVICE_B_NAME}")

        service = ServiceBInterface()
        service.export_to_dbus("/")

        print("READY", flush=True)

        # Run forever
        while True:
            await asyncio.sleep(3600)

    if __name__ == "__main__":
        asyncio.run(main())
    '''
)


class WorkerProcess:
    """Manages a worker subprocess running a D-Bus service."""

    def __init__(self, script: str, name: str):
        self.script = script
        self.name = name
        self.proc: subprocess.Popen | None = None
        self.stdout_lines: List[str] = []
        self.stderr_output: str = ""

    def start(self, timeout: float = 10.0) -> None:
        """Start the worker process and wait for READY signal."""
        self.proc = subprocess.Popen(
            [sys.executable, "-c", self.script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
        )

        # Wait for READY signal with timeout
        import select

        ready = select.select([self.proc.stdout], [], [], timeout)
        if not ready[0]:
            self.terminate()
            raise RuntimeError(
                f"Worker {self.name} did not become ready within {timeout}s"
            )

        line = self.proc.stdout.readline().decode().strip()
        self.stdout_lines.append(line)

        if line != "READY":
            self.terminate()
            raise RuntimeError(f"Worker {self.name} sent unexpected output: {line!r}")

    def terminate(self) -> None:
        """Terminate the worker process."""
        if self.proc is None:
            return

        self.proc.terminate()
        try:
            stdout, stderr = self.proc.communicate(timeout=5)
            self.stderr_output = stderr.decode()
            if stdout:
                self.stdout_lines.extend(stdout.decode().splitlines())
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.communicate()

    @property
    def returncode(self) -> int | None:
        """Get the return code if process has terminated."""
        if self.proc is None:
            return None
        return self.proc.poll()


class TestNestedDbusCallsStress(IsolatedDbusTestCase):
    """
    Test for nested D-Bus calls across separate processes.

    This test reproduces issues where nested D-Bus calls cause failures
    under stress:
    - "Task was destroyed but it is pending!" warnings
    - GeneratorExit thrown to async code unexpectedly
    - Event loop collapse/strange async behavior
    """

    worker_c: WorkerProcess
    worker_b: WorkerProcess

    def setUp(self) -> None:
        super().setUp()
        # Start worker processes
        self.worker_c = WorkerProcess(SERVICE_C_SCRIPT, "ServiceC")
        self.worker_b = WorkerProcess(SERVICE_B_SCRIPT, "ServiceB")

        try:
            # Start ServiceC first (terminal service)
            self.worker_c.start()
            # Then start ServiceB (which depends on ServiceC)
            self.worker_b.start()
        except Exception:
            self._cleanup_workers()
            raise

    def tearDown(self) -> None:
        self._cleanup_workers()
        super().tearDown()

    def _cleanup_workers(self) -> None:
        """Terminate all worker processes."""
        if hasattr(self, "worker_b"):
            self.worker_b.terminate()
        if hasattr(self, "worker_c"):
            self.worker_c.terminate()

    async def test_nested_calls_basic(self) -> None:
        """Basic sanity test for nested D-Bus calls (single call)."""
        proxy_b = ServiceBInterface.new_proxy(SERVICE_B_NAME, "/")

        result = await asyncio.wait_for(proxy_b.call_c(42, "hello"), timeout=10.0)

        self.assertEqual(result, "B:42:C:42:5", f"Unexpected result: {result!r}")

    async def test_nested_calls_sequential(self) -> None:
        """Test sequential nested calls (no concurrency)."""
        proxy_b = ServiceBInterface.new_proxy(SERVICE_B_NAME, "/")

        for i in range(20):
            result = await asyncio.wait_for(
                proxy_b.call_c(i, "x" * (i * 10 + 1)), timeout=10.0
            )
            expected = f"B:{i}:C:{i}:{i * 10 + 1}"
            self.assertEqual(
                result, expected, f"Call {i}: expected {expected!r}, got {result!r}"
            )

    async def test_nested_calls_stress_light(self) -> None:
        """Light stress test: 10 concurrent calls, 3 rounds."""
        await self._run_stress_test(concurrent=10, rounds=3, payload_size=100)

    async def test_nested_calls_stress_medium(self) -> None:
        """Medium stress test: 25 concurrent calls, 3 rounds."""
        await self._run_stress_test(concurrent=25, rounds=3, payload_size=1000)

    async def test_nested_calls_stress_heavy(self) -> None:
        """Heavy stress test: 50 concurrent calls, 5 rounds."""
        await self._run_stress_test(concurrent=50, rounds=5, payload_size=100)

    async def test_nested_calls_stress_extreme(self) -> None:
        """Extreme stress test: 100 concurrent calls, 3 rounds."""
        await self._run_stress_test(concurrent=100, rounds=3, payload_size=100)

    async def _run_stress_test(
        self, concurrent: int, rounds: int, payload_size: int
    ) -> None:
        """
        Run stress test with given parameters.

        Fires many concurrent calls through the chain:
            Test -> ServiceB -> ServiceC -> ServiceB -> Test

        Detects:
        - Timeouts (calls that don't complete)
        - Exceptions/errors
        - Task destruction warnings
        - Worker process crashes
        """
        # Create proxy to ServiceB
        proxy_b = ServiceBInterface.new_proxy(SERVICE_B_NAME, "/")

        # Verify connectivity first
        pong = await asyncio.wait_for(proxy_b.ping(), timeout=5.0)
        self.assertEqual(pong, "pong", "ServiceB not responding")

        # Track results
        errors: List[Exception] = []
        timeouts = 0
        completed = 0

        # Capture warnings
        with warnings.catch_warnings(record=True) as warning_list:
            warnings.simplefilter("always")

            for round_num in range(rounds):
                payload = "x" * payload_size
                tasks = []

                for i in range(concurrent):
                    call_id = round_num * concurrent + i

                    async def make_call(n: int, p: str) -> str:
                        return await proxy_b.call_c(n, p)

                    task = asyncio.create_task(
                        asyncio.wait_for(make_call(call_id, payload), timeout=30.0)
                    )
                    tasks.append((call_id, task))

                # Gather results
                results = await asyncio.gather(
                    *[t for _, t in tasks], return_exceptions=True
                )

                for (call_id, _), result in zip(tasks, results):
                    if isinstance(result, asyncio.TimeoutError):
                        timeouts += 1
                        errors.append(
                            Exception(f"Timeout on call {call_id} in round {round_num}")
                        )
                    elif isinstance(result, Exception):
                        errors.append(result)
                    else:
                        # Verify result format
                        expected_prefix = f"B:{call_id}:C:{call_id}:"
                        if not result.startswith(expected_prefix):
                            errors.append(
                                Exception(
                                    f"Unexpected result for call {call_id}: {result!r}"
                                )
                            )
                        else:
                            completed += 1

            # Check for task destruction warnings
            task_warnings = [
                w
                for w in warning_list
                if "Task was destroyed" in str(w.message)
                or "GeneratorExit" in str(w.message)
            ]

        # Check worker health
        worker_errors = []
        for name, worker in [("B", self.worker_b), ("C", self.worker_c)]:
            if worker.returncode is not None and worker.returncode != 0:
                worker_errors.append(
                    f"Worker {name} crashed with code {worker.returncode}: "
                    f"{worker.stderr_output[:500]}"
                )

        # Build detailed failure message
        total_calls = concurrent * rounds
        failure_details = []

        if timeouts > 0:
            failure_details.append(f"Timeouts: {timeouts}/{total_calls}")

        if errors:
            failure_details.append(f"Errors ({len(errors)}): {errors[:5]}")

        if task_warnings:
            failure_details.append(
                f"Task warnings ({len(task_warnings)}): "
                f"{[str(w.message) for w in task_warnings[:3]]}"
            )

        if worker_errors:
            failure_details.append(f"Worker crashes: {worker_errors}")

        # Assertions
        self.assertFalse(
            failure_details,
            f"Nested D-Bus call stress test failed!\n"
            f"Completed: {completed}/{total_calls}\n"
            f"Details:\n" + "\n".join(f"  - {d}" for d in failure_details),
        )

        self.assertEqual(
            completed, total_calls, f"Only {completed}/{total_calls} calls completed"
        )
