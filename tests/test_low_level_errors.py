# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020-2022 igo95862
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

from asyncio import get_running_loop, wait_for
from typing import Any

from aiodbus import DbusInterfaceCommonAsync, dbus_method, dbus_property
from aiodbus.bus import get_default_bus
from aiodbus.dbus_common_elements import DbusLocalObjectMeta
from aiodbus.exceptions import DbusFailedError, DbusMethodError
from aiodbus.unittest import IsolatedDbusTestCase

HELLO_WORLD = "Hello, world!"


class DbusDerivePropertydError(DbusMethodError, name="org.example.PropertyError"): ...


class IndependentError(Exception): ...


GOOD_STR = "Good"


class InterfaceWithErrors(
    DbusInterfaceCommonAsync,
    interface_name="org.example.errors",
):
    @dbus_property("s")
    def indep_err_getter(self) -> str:
        raise IndependentError

    @dbus_property("s")
    def derrive_err_getter(self) -> str:
        raise DbusDerivePropertydError

    @dbus_method(result_signature="s")
    async def hello_error(self) -> str:
        raise AttributeError

    @dbus_method(result_signature="s")
    async def hello_world(self) -> str:
        return HELLO_WORLD

    @dbus_property("s")
    def indep_err_setable(self) -> str:
        return GOOD_STR

    @indep_err_setable.setter
    def indep_err_setter(self, new_value: str) -> None:
        raise IndependentError

    @dbus_property("s")
    def derrive_err_settable(self) -> str:
        return GOOD_STR

    @derrive_err_settable.setter
    def derrive_err_setter(self, new_value: str) -> None:
        raise DbusDerivePropertydError


class TestLowLevelErrors(IsolatedDbusTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()

        await get_default_bus().request_name("org.test")
        self.test_object = InterfaceWithErrors()
        self.test_object.export_to_dbus("/")

        self.test_object_connection = InterfaceWithErrors.new_proxy("org.test", "/")

        loop = get_running_loop()

        def silence_exceptions(*args: Any, **kwrags: Any) -> None: ...

        loop.set_exception_handler(silence_exceptions)

    async def test_property_getter_independent_error(self) -> None:
        with self.assertRaises(DbusFailedError) as cm:
            await wait_for(
                self.test_object_connection.indep_err_getter.get(),
                timeout=1,
            )

        should_be_dbus_failed = cm.exception
        self.assertIs(should_be_dbus_failed.__class__, DbusFailedError)

        await self.test_object_connection.hello_world()

    async def test_generic_error_is_returned_as_dbus_failed(self) -> None:
        with self.assertRaises(DbusFailedError) as cm:
            await wait_for(
                self.test_object_connection.hello_error(),
                timeout=1,
            )

    async def test_property_getter_derived_error(self) -> None:
        with self.assertRaises(DbusDerivePropertydError):
            await wait_for(
                self.test_object_connection.derrive_err_getter.get(),
                timeout=1,
            )

        await self.test_object_connection.hello_world()

    async def test_property_setter_independent_error(self) -> None:

        self.assertEqual(
            await wait_for(
                self.test_object_connection.indep_err_setable.get(),
                timeout=1,
            ),
            GOOD_STR,
        )

        with self.assertRaises(DbusFailedError) as cm:
            await wait_for(
                self.test_object_connection.indep_err_setable.set("Test"),
                timeout=1,
            )

        should_be_dbus_failed = cm.exception
        self.assertIs(should_be_dbus_failed.__class__, DbusFailedError)

        await self.test_object_connection.hello_world()

    async def test_property_setter_derived_error(self) -> None:

        self.assertEqual(
            await wait_for(
                self.test_object_connection.derrive_err_settable.get(),
                timeout=1,
            ),
            GOOD_STR,
        )

        with self.assertRaises(DbusDerivePropertydError):
            await wait_for(
                self.test_object_connection.derrive_err_settable.set("Test"),
                timeout=1,
            )

        await self.test_object_connection.hello_world()

    async def test_property_callback_error(self) -> None:
        dbus_local_meta = self.test_object._dbus
        if not isinstance(dbus_local_meta, DbusLocalObjectMeta):
            raise TypeError
        interface = dbus_local_meta.activated_interfaces[0]
        interface.property_get_dict.pop(b"DerriveErrSettable")

        with self.assertRaises(DbusFailedError):
            await wait_for(
                self.test_object_connection.derrive_err_settable,
                timeout=1,
            )

    async def test_method_callback_error(self) -> None:
        TEST_KEY = b"HelloWorld"
        dbus_local_meta = self.test_object._dbus
        if not isinstance(dbus_local_meta, DbusLocalObjectMeta):
            raise TypeError
        interface = dbus_local_meta.activated_interfaces[0]
        interface.method_dict.pop(TEST_KEY)

        with self.assertRaises(DbusFailedError):
            await wait_for(
                self.test_object_connection.hello_world(),
                timeout=1,
            )

        interface.method_dict[TEST_KEY] = None

        def test_raise(*args: Any, **kwargs: Any) -> None:
            raise DbusDerivePropertydError

        interface.method_dict[TEST_KEY] = test_raise
        with self.assertRaises(DbusDerivePropertydError):
            await wait_for(
                self.test_object_connection.hello_world(),
                timeout=1,
            )
