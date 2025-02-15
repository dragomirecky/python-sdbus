# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2024 igo95862
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

from typing import TYPE_CHECKING

from aiodbus import DbusInterfaceCommon, dbus_method, dbus_property, dbus_signal

if TYPE_CHECKING:
    from typing import List


# These functions are not meant to be executed
# but exist to be type checked.


class InterfaceTestTyping(
    DbusInterfaceCommon,
    interface_name="example.com",
):

    @dbus_method(result_signature="as")
    async def get_str_list_method(self) -> List[str]:
        raise NotImplementedError

    @dbus_property("as")
    def str_list_property(self) -> List[str]:
        raise NotImplementedError

    @dbus_signal("as")
    def str_list_signal(self) -> List[str]:
        raise NotImplementedError


async def check_async_interface_method_typing(
    test_interface: InterfaceTestTyping,
) -> None:

    should_be_list = await test_interface.get_str_list_method()
    should_be_list.append("test")

    for x in should_be_list:
        x.capitalize()


async def check_async_interface_property_typing(
    test_interface: InterfaceTestTyping,
) -> None:

    should_be_list = await test_interface.str_list_property
    should_be_list.append("test")

    for x in should_be_list:
        x.capitalize()

    should_be_list2 = await test_interface.str_list_property.get()
    should_be_list2.append("test")

    for x in should_be_list2:
        x.capitalize()

    await test_interface.str_list_property.set(["test", "foobar"])


async def check_async_interface_signal_typing(
    test_interface: InterfaceTestTyping,
) -> None:

    async for ls in test_interface.str_list_signal:
        ls.append("test")
        for x in ls:
            x.capitalize()

    async for ls2 in test_interface.str_list_signal.catch():
        ls2.append("test")
        for x2 in ls2:
            x2.capitalize()

    async for p1, ls3 in test_interface.str_list_signal.catch_anywhere():
        p1.capitalize()
        ls3.append("test")
        for x3 in ls3:
            x3.capitalize()

    async for p2, ls4 in InterfaceTestTyping.str_list_signal.catch_anywhere("org.example"):
        p2.capitalize()
        ls4.append("test")
        for x4 in ls4:
            x4.capitalize()

    test_interface.str_list_signal.emit(["test", "foobar"])


async def check_async_element_class_access_typing() -> None:

    test_list: List[str] = []

    # TODO: Fix dbus async method typing
    # test_list.append(
    #     TestTypingAsync.get_str_list_method.method_name
    # )
    test_list.append(InterfaceTestTyping.str_list_property.name)
    test_list.append(InterfaceTestTyping.str_list_signal.name)
