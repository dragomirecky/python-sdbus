# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020-2024 igo95862

# This file is part of python-sdbus

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

from aiodbus.dbus_common_funcs import _parse_properties_vardict
from aiodbus.interface.base import DbusInterfaceBaseAsync
from aiodbus.member.method import dbus_method_async
from aiodbus.member.signal import dbus_signal_async

if TYPE_CHECKING:
    from typing import Any, Dict, List, Tuple

    DBUS_PROPERTIES_CHANGED_TYPING = (
        Tuple[
            str,
            Dict[str, Tuple[str, Any]],
            List[str],
        ]
    )



