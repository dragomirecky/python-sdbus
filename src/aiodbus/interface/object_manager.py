# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020-2024 igo95862
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

from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, override

from aiodbus import get_default_bus
from aiodbus.bus import Dbus
from aiodbus.interface.common import DbusInterfaceCommon
from aiodbus.interface.properties import PropertiesDict
from aiodbus.member.method import dbus_method
from aiodbus.member.signal import DbusSignal, dbus_signal

if TYPE_CHECKING:
    from aiodbus.interface.base import DbusInterface


@dataclass(frozen=True)
class InterfacesAddedData:
    path: str
    interfaces: Dict[str, PropertiesDict]


def parse_interfaces_added(data: Tuple[str, Dict[str, Dict[str, Any]]]) -> InterfacesAddedData:
    path, interfaces_and_properties = data
    interfaces: Dict[str, PropertiesDict] = {}
    for interface_name, properties_raw in interfaces_and_properties.items():
        properties = PropertiesDict()
        for member_name, variant in properties_raw.items():
            properties[(interface_name, member_name)] = variant[1]
        interfaces[interface_name] = properties
    return InterfacesAddedData(path, interfaces)


@dataclass(frozen=True)
class InterfacesRemovedData:
    path: str
    interfaces: List[str]


def parse_interfaces_removed(data: Tuple[str, List[str]]) -> InterfacesRemovedData:
    path, interfaces = data
    return InterfacesRemovedData(path, interfaces)


class DbusObjectManagerInterface(
    DbusInterfaceCommon,
    interface_name="org.freedesktop.DBus.ObjectManager",
    serving_enabled=False,
):
    def __init__(self) -> None:
        super().__init__()
        self._managed_objects: Dict[str, DbusInterface] = {}

    interfaces_removed = DbusSignal[Tuple[str, List[str]]]("oao")

    @dbus_method(result_signature="a{oa{sa{sv}}}")
    async def get_managed_objects(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        raise NotImplementedError

    @dbus_signal("oa{sa{sv}}")
    def interfaces_added(self) -> Tuple[str, Dict[str, Dict[str, Any]]]:
        raise NotImplementedError

    @override
    def export_to_dbus(
        self,
        object_path: str,
        bus: Optional[Dbus] = None,
        manager: Optional[DbusObjectManagerInterface] = None,
    ) -> ExitStack:
        if bus is None:
            bus = get_default_bus()
        with super().export_to_dbus(
            object_path,
            bus,
        ) as exit_stack:
            exit_stack.callback(bus.export_object_manager(path=object_path).close)
            return exit_stack.pop_all()
