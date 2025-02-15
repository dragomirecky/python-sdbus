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

from typing import Dict, List, Optional

from aiodbus.bus import Dbus, Interface, get_default_bus


class DbusRemoteObjectMeta:
    def __init__(
        self,
        service_name: str,
        object_path: str,
        bus: Optional[Dbus] = None,
    ):
        self.service_name = service_name
        self.object_path = object_path
        self.attached_bus = bus if bus is not None else get_default_bus()


class DbusLocalObjectMeta:
    def __init__(self) -> None:
        self.activated_interfaces: List[Interface] = []
        self.serving_object_path: Optional[str] = None
        self.attached_bus: Optional[Dbus] = None


class DbusClassMeta:
    def __init__(
        self,
        interface_name: str,
        serving_enabled: bool,
    ) -> None:
        self.interface_name = interface_name
        self.serving_enabled = serving_enabled
        self.dbus_member_to_python_attr: Dict[str, str] = {}
        self.python_attr_to_dbus_member: Dict[str, str] = {}
