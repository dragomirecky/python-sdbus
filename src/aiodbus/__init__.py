# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020-2022 igo95862

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

from _sdbus import (
    DbusDeprecatedFlag,
    DbusHiddenFlag,
    DbusNoReplyFlag,
    DbusPropertyConstFlag,
    DbusPropertyEmitsChangeFlag,
    DbusPropertyEmitsInvalidationFlag,
    DbusPropertyExplicitFlag,
    DbusSensitiveFlag,
    DbusUnprivilegedFlag,
    SdBus,
    SdBusBaseError,
    SdBusLibraryError,
    SdBusUnmappedMessageError,
    decode_object_path,
    encode_object_path,
    map_exception_to_dbus_error,
    sd_bus_open,
    sd_bus_open_system,
    sd_bus_open_system_machine,
    sd_bus_open_system_remote,
    sd_bus_open_user,
    sd_bus_open_user_machine,
)
from aiodbus.interface.common import DbusInterfaceCommonAsync
from aiodbus.interface.object_manager import DbusObjectManagerInterfaceAsync
from aiodbus.member.method import (
    dbus_method,
    dbus_method_override,
    get_current_message,
)
from aiodbus.member.property import dbus_property, dbus_property_async_override
from aiodbus.member.signal import dbus_signal

from .dbus_common_funcs import (
    get_default_bus,
    request_default_bus_name,
    request_default_bus_name,
    set_default_bus,
)
from .dbus_exceptions import (
    DbusAccessDeniedError,
    DbusAddressInUseError,
    DbusAuthFailedError,
    DbusBadAddressError,
    DbusDisconnectedError,
    DbusFailedError,
    DbusFileExistsError,
    DbusFileNotFoundError,
    DbusIOError,
    DbusInconsistentMessageError,
    DbusInteractiveAuthorizationRequiredError,
    DbusInvalidArgsError,
    DbusInvalidFileContentError,
    DbusInvalidSignatureError,
    DbusLimitsExceededError,
    DbusMatchRuleInvalidError,
    DbusMatchRuleNotFound,
    DbusNameHasNoOwnerError,
    DbusNoMemoryError,
    DbusNoNetworkError,
    DbusNoReplyError,
    DbusNoServerError,
    DbusNotSupportedError,
    DbusPropertyReadOnlyError,
    DbusServiceUnknownError,
    DbusTimeoutError,
    DbusUnixProcessIdUnknownError,
    DbusUnknownInterfaceError,
    DbusUnknownMethodError,
    DbusUnknownObjectError,
    DbusUnknownPropertyError,
)

__all__ = (
    'get_default_bus', 'request_default_bus_name',
    'request_default_bus_name', 'set_default_bus',

    'DbusAccessDeniedError', 'DbusAddressInUseError',
    'DbusAuthFailedError', 'DbusBadAddressError',
    'DbusDisconnectedError', 'DbusFailedError',
    'DbusFileExistsError', 'DbusFileNotFoundError',
    'DbusInconsistentMessageError',
    'DbusInteractiveAuthorizationRequiredError',
    'DbusInvalidArgsError',
    'DbusInvalidFileContentError',
    'DbusInvalidSignatureError', 'DbusIOError',
    'DbusLimitsExceededError',
    'DbusMatchRuleInvalidError', 'DbusMatchRuleNotFound',
    'DbusNameHasNoOwnerError', 'DbusNoMemoryError',
    'DbusNoNetworkError', 'DbusNoReplyError',
    'DbusNoServerError', 'DbusNotSupportedError',
    'DbusPropertyReadOnlyError',
    'DbusServiceUnknownError', 'DbusTimeoutError',
    'DbusUnixProcessIdUnknownError',
    'DbusUnknownInterfaceError',
    'DbusUnknownMethodError', 'DbusUnknownObjectError',
    'DbusUnknownPropertyError',

    'DbusInterfaceCommonAsync',
    'DbusObjectManagerInterfaceAsync',

    'dbus_method',
    'dbus_method_override',

    'dbus_property',
    'dbus_property_async_override',
    'get_current_message',

    'dbus_signal',

    'DbusDeprecatedFlag',
    'DbusHiddenFlag',
    'DbusNoReplyFlag',
    'DbusPropertyConstFlag',
    'DbusPropertyEmitsChangeFlag',
    'DbusPropertyEmitsInvalidationFlag',
    'DbusPropertyExplicitFlag',
    'DbusSensitiveFlag',
    'DbusUnprivilegedFlag',
    'SdBus',
    'SdBusBaseError',
    'SdBusLibraryError',
    'SdBusUnmappedMessageError',
    'decode_object_path',
    'encode_object_path',
    'map_exception_to_dbus_error',
    'sd_bus_open',
    'sd_bus_open_system',
    'sd_bus_open_system_machine',
    'sd_bus_open_system_remote',
    'sd_bus_open_user',
    'sd_bus_open_user_machine',
)
