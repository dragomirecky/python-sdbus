# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2022 igo95862
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
from __future__ import annotations

from asyncio import Event, TimeoutError, wait_for
from contextlib import ExitStack, contextmanager
from operator import setitem
from os import environ, kill
from pathlib import Path
from signal import SIGTERM
from subprocess import DEVNULL
from subprocess import run as subprocess_run
from tempfile import TemporaryDirectory
from typing import Any, AsyncContextManager, Iterator, List, Optional, TypeVar, Union
from unittest import IsolatedAsyncioTestCase
from weakref import ref as weak_ref

from _sdbus import SdBus, SdBusMessage, SdBusSlot
from aiodbus.bus import Dbus, connect, set_default_bus
from aiodbus.handle import Closeable
from aiodbus.member.signal import (
    DbusBoundSignal,
    DbusLocalSignal,
    DbusProxySignal,
    DbusSignal,
)

T = TypeVar("T")


dbus_config = """
<busconfig>
  <type>session</type>
  <pidfile>{pidfile_path}</pidfile>
  <auth>EXTERNAL</auth>
  <listen>unix:path={socket_path}</listen>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
"""


class DbusSignalRecorderBase:
    def __init__(
        self,
        timeout: Union[int, float],
    ):
        self._timeout = timeout
        self._captured_data: List[Any] = []
        self._ready_event = Event()
        self._callback_method = self._callback

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def __aenter__(self) -> DbusSignalRecorderBase:
        raise NotImplementedError

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        if exc_type is not None:
            return

        try:
            await wait_for(self._ready_event.wait(), timeout=self._timeout)
        except TimeoutError:
            raise AssertionError("D-Bus signal not captured.") from None

    def _callback(self, data: Any) -> None:
        if isinstance(data, SdBusMessage):
            data = data.get_contents()

        self._captured_data.append(data)
        self._ready_event.set()

    @property
    def output(self) -> List[Any]:
        return self._captured_data.copy()


class DbusSignalRecorderRemote(DbusSignalRecorderBase):
    def __init__(
        self,
        timeout: Union[int, float],
        bus: Dbus,
        remote_signal: DbusProxySignal[Any],
    ):
        super().__init__(timeout)
        self._bus = bus
        self._handle: Optional[Closeable] = None
        self._remote_signal = remote_signal

    async def __aenter__(self) -> DbusSignalRecorderBase:
        self._handle = await self._remote_signal._register_match_slot(
            self._bus,
            self._callback_method,
        )

        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        try:
            await super().__aexit__(exc_type, exc_value, traceback)
        finally:
            if self._handle is not None:
                self._handle.close()


class DbusSignalRecorderLocal(DbusSignalRecorderBase):
    def __init__(
        self,
        timeout: Union[int, float],
        local_signal: DbusLocalSignal[Any],
    ):
        super().__init__(timeout)
        self._local_signal_ref: weak_ref[DbusSignal[Any]] = weak_ref(local_signal.dbus_signal)

    async def __aenter__(self) -> DbusSignalRecorderBase:
        local_signal = self._local_signal_ref()

        if local_signal is None:
            raise RuntimeError

        local_signal.local_callbacks.add(self._callback_method)
        return self


@contextmanager
def _isolated_dbus(
    dbus_executable_name: str = "dbus-daemon",
) -> Iterator[Dbus]:
    with ExitStack() as exit_stack:
        temp_dir_path = Path(exit_stack.enter_context(TemporaryDirectory(prefix="python-sdbus-")))

        dbus_socket_path = temp_dir_path / "test_dbus.socket"
        pid_path = temp_dir_path / "dbus.pid"
        dbus_config_file = temp_dir_path / "dbus.config"
        dbus_config_file.write_text(
            dbus_config.format(socket_path=dbus_socket_path, pidfile_path=pid_path)
        )

        subprocess_run(
            args=(
                dbus_executable_name,
                "--config-file",
                dbus_config_file,
                "--fork",
            ),
            stdin=DEVNULL,
            check=True,
        )
        # D-Bus daemon exits once it forks and is initialized.

        dbus_pid = int(pid_path.read_text())
        exit_stack.callback(kill, dbus_pid, SIGTERM)

        old_session_bus_address = environ.get("DBUS_SESSION_BUS_ADDRESS")
        if old_session_bus_address is not None:
            exit_stack.callback(
                setitem,
                environ,
                "DBUS_SESSION_BUS_ADDRESS",
                old_session_bus_address,
            )
        else:
            exit_stack.callback(
                environ.pop,
                "DBUS_SESSION_BUS_ADDRESS",
            )
        environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={dbus_socket_path}"

        bus = connect("session")
        set_default_bus(bus)
        yield bus


class IsolatedDbusTestCase(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # TODO: Use enterContext from Python 3.11
        _isolated_dbus_cm = _isolated_dbus()
        self.bus = _isolated_dbus_cm.__enter__()
        self.sdbus = self.bus._sdbus
        self.addCleanup(_isolated_dbus_cm.__exit__, None, None, None)

    async def asyncSetUp(self) -> None:
        set_default_bus(self.bus)

    def assertDbusSignalEmits(
        self,
        signal: DbusBoundSignal[Any],
        timeout: Union[int, float] = 1,
    ) -> AsyncContextManager[DbusSignalRecorderBase]:

        if isinstance(signal, DbusLocalSignal):
            return DbusSignalRecorderLocal(timeout, signal)
        elif isinstance(signal, DbusProxySignal):
            return DbusSignalRecorderRemote(timeout, self.bus, signal)
        else:
            raise TypeError("Unknown or unsupported signal class.")
