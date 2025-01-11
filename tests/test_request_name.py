# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2023 igo95862
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

from asyncio import get_running_loop, sleep, wait_for
from unittest import main

from _sdbus import NameAllowReplacementFlag, NameQueueFlag
from aiodbus import request_default_bus_name, sd_bus_open_user
from aiodbus.exceptions import (
    DbusError,
    SdBusRequestNameAlreadyOwnerError,
    SdBusRequestNameError,
    SdBusRequestNameExistsError,
    SdBusRequestNameInQueueError,
)
from aiodbus.interface.daemon import FreedesktopDbus
from aiodbus.unittest import IsolatedDbusTestCase

TEST_BUS_NAME = "com.example.test"
TEST_BUS_NAME_regex_match = TEST_BUS_NAME.replace(".", r"\.")


class TestRequestNameLowLevel(IsolatedDbusTestCase):
    def test_request_name_exception_tree(self) -> None:
        # Test that SdBusRequestNameError is super class
        # of other request name exceptions
        self.assertTrue(
            issubclass(
                SdBusRequestNameAlreadyOwnerError,
                SdBusRequestNameError,
            )
        )
        self.assertTrue(
            issubclass(
                SdBusRequestNameExistsError,
                SdBusRequestNameError,
            )
        )
        self.assertTrue(
            issubclass(
                SdBusRequestNameInQueueError,
                SdBusRequestNameError,
            )
        )
        # Test the opposite
        self.assertFalse(
            issubclass(
                SdBusRequestNameAlreadyOwnerError,
                SdBusRequestNameExistsError,
            )
        )
        self.assertFalse(
            issubclass(
                SdBusRequestNameInQueueError,
                SdBusRequestNameExistsError,
            )
        )
        self.assertFalse(
            issubclass(
                SdBusRequestNameInQueueError,
                SdBusRequestNameAlreadyOwnerError,
            )
        )

    async def test_name_exists_async(self) -> None:
        extra_bus = sd_bus_open_user()
        await self.bus.request_name(TEST_BUS_NAME, 0)

        with self.assertRaises(SdBusRequestNameExistsError):
            await wait_for(
                extra_bus.request_name(TEST_BUS_NAME, 0),
                timeout=1,
            )

    async def test_name_already_async(self) -> None:
        await self.bus.request_name(TEST_BUS_NAME, 0)

        with self.assertRaises(SdBusRequestNameAlreadyOwnerError):
            await wait_for(
                self.bus.request_name(TEST_BUS_NAME, 0),
                timeout=1,
            )

    async def test_name_queued_async(self) -> None:
        extra_bus = sd_bus_open_user()
        await self.bus.request_name(TEST_BUS_NAME, 0)

        with self.assertRaises(SdBusRequestNameInQueueError):
            await wait_for(
                extra_bus.request_name(TEST_BUS_NAME, NameQueueFlag),
                timeout=1,
            )

    async def test_name_other_error_async(self) -> None:
        extra_bus = sd_bus_open_user()
        extra_bus.close()

        with self.assertRaises(DbusError):
            await wait_for(
                extra_bus.request_name(TEST_BUS_NAME, 0),
                timeout=1,
            )


class TestRequestNameAsync(IsolatedDbusTestCase):
    async def test_request_name_replacement(self) -> None:
        extra_bus = sd_bus_open_user()
        await extra_bus.request_name(
            TEST_BUS_NAME,
            NameAllowReplacementFlag,
        )

        with self.assertRaises(SdBusRequestNameExistsError):
            await request_default_bus_name(TEST_BUS_NAME)

        await request_default_bus_name(
            TEST_BUS_NAME,
            replace_existing=True,
        )

    async def test_request_name_queue(self) -> None:
        extra_bus = sd_bus_open_user()
        await extra_bus.request_name(TEST_BUS_NAME, 0)

        with self.assertRaises(SdBusRequestNameInQueueError):
            await request_default_bus_name(
                TEST_BUS_NAME,
                queue=True,
            )

        async def catch_owner_changed() -> str:
            dbus = FreedesktopDbus()
            async for name, old, new in dbus.name_owner_changed:
                if name != TEST_BUS_NAME:
                    continue

                if old and new:
                    return new

            raise RuntimeError

        loop = get_running_loop()
        owner_changed_task = loop.create_task(catch_owner_changed())
        await sleep(0)

        extra_bus.close()

        await wait_for(owner_changed_task, timeout=0.5)

        with self.assertRaises(SdBusRequestNameAlreadyOwnerError):
            await request_default_bus_name(TEST_BUS_NAME)


if __name__ == "__main__":
    main()
