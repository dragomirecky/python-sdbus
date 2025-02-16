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

from gc import collect
from unittest import TestCase
from unittest import main as unittest_main

from aiodbus import (
    DbusDeprecatedFlag,
    DbusInterfaceCommon,
    DbusPropertyConstFlag,
    DbusPropertyEmitsChangeFlag,
    dbus_method,
    dbus_property,
    dbus_signal,
)
from aiodbus.bus.sdbus import SdBusInterfaceBuilder
from aiodbus.member.property import DbusProperty

from .common_test_util import skip_if_no_asserts, skip_if_no_name_validations


class SomeTestInterface(
    DbusInterfaceCommon,
    interface_name="org.example.good",
):
    @dbus_method(result_signature="i")
    async def test_int(self) -> int:
        return 1


class TestBadAsyncDbusClass(TestCase):
    def test_name_validations(self) -> None:
        skip_if_no_name_validations()

        with self.assertRaisesRegex(
            AssertionError,
            "^Invalid interface name",
        ):

            class BadInterfaceName(
                DbusInterfaceCommon,
                interface_name="0.test",
            ): ...

        with self.assertRaisesRegex(
            AssertionError,
            "^Invalid name",
        ):

            class BadMethodName(
                DbusInterfaceCommon,
                interface_name="org.example",
            ):
                @dbus_method(
                    result_signature="s",
                    name="🤫",
                )
                async def test(self) -> str:
                    return "test"

        with self.assertRaisesRegex(
            AssertionError,
            "^Invalid name",
        ):

            class BadPropertyName(
                DbusInterfaceCommon,
                interface_name="org.example",
            ):
                @dbus_property(
                    signature="s",
                    name="🤫",
                )
                def test(self) -> str:
                    return "test"

        with self.assertRaisesRegex(
            AssertionError,
            "^Invalid name",
        ):

            class BadSignalName(
                DbusInterfaceCommon,
                interface_name="org.example",
            ):
                @dbus_signal(
                    signature="s",
                    name="🤫",
                )
                def test(self) -> str:
                    raise NotImplementedError

    def test_property_flags(self) -> None:
        self.assertEqual(0, SdBusInterfaceBuilder._isolate_property_flags(DbusDeprecatedFlag))
        self.assertEqual(
            1,
            (
                SdBusInterfaceBuilder._isolate_property_flags(
                    DbusDeprecatedFlag | DbusPropertyEmitsChangeFlag
                )
            ).bit_count(),
        )
        self.assertEqual(
            2,
            (
                SdBusInterfaceBuilder._isolate_property_flags(
                    DbusDeprecatedFlag | DbusPropertyConstFlag | DbusPropertyEmitsChangeFlag
                )
            ).bit_count(),
        )

        with (
            self.subTest("Test incorrect flags"),
            self.assertRaisesRegex(
                AssertionError,
                "^Incorrect number of Property flags",
            ),
        ):
            skip_if_no_asserts()

            class InvalidPropertiesFlags(
                DbusInterfaceCommon, interface_name="org.test.invalidprop"
            ):
                @dbus_property(
                    "s",
                    const=True,
                    emits_change=True,
                )
                def test_constant(self) -> str:
                    return "a"

            local_object = InvalidPropertiesFlags()
            local_object.export_to_dbus("/")

        with self.subTest("Valid properties flags"):

            class ValidPropertiesFlags(DbusInterfaceCommon, interface_name="org.test.validprop"):
                @dbus_property(
                    "s",
                    deprecated=True,
                    emits_change=True,
                )
                def test_constant(self) -> str:
                    return "a"

    def test_dbus_elements_without_interface_name(self) -> None:
        with self.assertRaisesRegex(TypeError, "without interface name"):

            class NoInterfaceName(DbusInterfaceCommon):
                @dbus_method()
                async def example(self) -> None: ...

    def test_dbus_elements_without_interface_name_subclass(self) -> None:
        with self.assertRaisesRegex(TypeError, "without interface name"):

            class NoInterfaceName(SomeTestInterface):
                @dbus_method()
                async def example(self) -> None: ...

    def test_shared_parent_class(self) -> None:
        class One(SomeTestInterface): ...

        class Two(SomeTestInterface): ...

        class Shared(One, Two): ...

    def test_combined_collision(self) -> None:

        class One(
            DbusInterfaceCommon,
            interface_name="org.example.foo",
        ):
            @dbus_method()
            async def example(self) -> None: ...

        class Two(
            DbusInterfaceCommon,
            interface_name="org.example.bar",
        ):
            @dbus_method()
            async def example(self) -> None: ...

        with self.assertRaisesRegex(ValueError, "collision"):

            class Combined(One, Two): ...

    def test_class_cleanup(self) -> None:
        class One(
            DbusInterfaceCommon,
            interface_name="org.example.foo1",
        ): ...

        with self.assertRaises(ValueError):

            class Two(
                DbusInterfaceCommon,
                interface_name="org.example.foo1",
            ): ...

        del One
        collect()  # Let weak refs be processed

        class After(
            DbusInterfaceCommon,
            interface_name="org.example.foo1",
        ): ...


if __name__ == "__main__":
    unittest_main()
