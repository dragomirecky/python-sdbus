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

from functools import partial
from typing import TYPE_CHECKING, cast

from _sdbus import _SdBus
from aiodbus import get_default_bus
from aiodbus.bus import Dbus
from aiodbus.bus.sdbus import SdBus, _SdBus
from aiodbus.interface.base import DbusExportHandle, DbusInterface
from aiodbus.interface.common import DbusInterfaceCommon
from aiodbus.member.method import dbus_method
from aiodbus.member.signal import dbus_signal

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, List, Optional, Tuple

    from _sdbus import SdBusSlot


class CloseableFromCallback:
    def __init__(self, callback: Callable[[], None]) -> None:
        self.close = callback


class DbusObjectManagerInterface(
    DbusInterfaceCommon,
    interface_name="org.freedesktop.DBus.ObjectManager",
    serving_enabled=False,
):
    def __init__(self) -> None:
        super().__init__()
        self._object_manager_slot: Optional[SdBusSlot] = None
        self._managed_object_to_path: Dict[DbusInterface, str] = {}

    @dbus_method(result_signature="a{oa{sa{sv}}}")
    async def get_managed_objects(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        raise NotImplementedError

    @dbus_signal("oa{sa{sv}}")
    def interfaces_added(self) -> Tuple[str, Dict[str, Dict[str, Any]]]:
        raise NotImplementedError

    @dbus_signal("oao")
    def interfaces_removed(self) -> Tuple[str, List[str]]:
        raise NotImplementedError

    def _get_sdbus(self, bus: Optional[Dbus] = None) -> _SdBus:
        # TODO: remove direct access to sdbus
        if bus is None:
            bus = get_default_bus()
        return cast(SdBus, bus)._sdbus

    def export_to_dbus(
        self,
        object_path: str,
        bus: Optional[Dbus] = None,
    ) -> DbusExportHandle:
        if bus is None:
            bus = get_default_bus()

        export_handle = super().export_to_dbus(
            object_path,
            bus,
        )
        slot = self._get_sdbus(bus).add_object_manager(object_path)
        self._object_manager_slot = slot
        export_handle.append(slot)
        return export_handle

    def export_with_manager(
        self,
        object_path: str,
        object_to_export: DbusInterface,
        bus: Optional[Dbus] = None,
    ) -> DbusExportHandle:
        if self._object_manager_slot is None:
            raise RuntimeError("ObjectManager not intitialized")

        if bus is None:
            bus = get_default_bus()

        export_handle = object_to_export.export_to_dbus(
            object_path,
            bus,
        )
        export_handle.append(
            CloseableFromCallback(
                partial(self.remove_managed_object, object_to_export),
            )
        )
        self._get_sdbus(bus).emit_object_added(object_path)
        self._managed_object_to_path[object_to_export] = object_path
        return export_handle

    def remove_managed_object(self, managed_object: DbusInterface) -> None:
        if self._dbus.attached_bus is None:
            raise RuntimeError("Object manager not exported")

        removed_path = self._managed_object_to_path.pop(managed_object)
        self._get_sdbus(self._dbus.attached_bus).emit_object_removed(removed_path)
