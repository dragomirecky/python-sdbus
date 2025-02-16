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

from aiodbus.bus import (
    Dbus,
    connect,
    get_current_message,
    get_default_bus,
    set_default_bus,
)
from aiodbus.bus.message import Message, get_current_message
from aiodbus.handle import DbusExportHandle
from aiodbus.interface.base import DbusInterface
from aiodbus.interface.common import DbusInterfaceCommon
from aiodbus.interface.object_manager import DbusObjectManagerInterface
from aiodbus.member.method import DbusMethod, dbus_method
from aiodbus.member.property import DbusProperty, dbus_property
from aiodbus.member.signal import DbusSignal, dbus_signal

from .exceptions import (
    AccessDeniedError,
    AddressInUseError,
    AuthFailedError,
    BadAddressError,
    CallFailedError,
    DbusError,
    DisconnectedError,
    FileExistsError,
    FileNotFoundError,
    InconsistentMessageError,
    InteractiveAuthorizationRequiredError,
    InvalidArgsError,
    InvalidFileContentError,
    InvalidSignatureError,
    IOError,
    LimitsExceededError,
    MatchRuleInvalidError,
    MatchRuleNotFoundError,
    MethodCallError,
    NameHasNoOwnerError,
    NoMemoryError,
    NoNetworkError,
    NoReplyError,
    NoServerError,
    NotSupportedError,
    PropertyReadOnlyError,
    ServiceUnknownError,
    TimeoutError,
    UknownMethodError,
    UnixProcessIdUnknown,
    UnknownInterfaceError,
    UnknownObjectError,
    UnknownPropertyError,
)

__all__ = (
    "AccessDeniedError",
    "AddressInUseError",
    "AuthFailedError",
    "BadAddressError",
    "DisconnectedError",
    "CallFailedError",
    "FileExistsError",
    "FileNotFoundError",
    "InconsistentMessageError",
    "InteractiveAuthorizationRequiredError",
    "InvalidArgsError",
    "InvalidFileContentError",
    "InvalidSignatureError",
    "IOError",
    "LimitsExceededError",
    "MatchRuleInvalidError",
    "MatchRuleNotFoundError",
    "NameHasNoOwnerError",
    "NoMemoryError",
    "NoNetworkError",
    "NoReplyError",
    "NoServerError",
    "NotSupportedError",
    "PropertyReadOnlyError",
    "ServiceUnknownError",
    "MethodCallError",
    "TimeoutError",
    "UnixProcessIdUnknown",
    "UnknownInterfaceError",
    "UknownMethodError",
    "UnknownObjectError",
    "UnknownPropertyError",
    "DbusInterfaceCommon",
    "DbusObjectManagerInterface",
    "dbus_method",
    "dbus_property",
    "get_current_message",
    "dbus_signal",
    "connect",
    "get_default_bus",
    "set_default_bus",
    "Dbus",
    "DbusMethod",
    "DbusProperty",
    "DbusSignal",
    "DbusInterface",
    "Message",
    "get_current_message",
    "DbusExportHandle",
    "DbusError",
)
