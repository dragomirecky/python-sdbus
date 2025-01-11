# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020, 2021 igo95862
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

from typing import ClassVar, Dict, Type


class DbusError(Exception): ...


class SdBusRequestNameError(DbusError): ...


class SdBusRequestNameAlreadyOwnerError(SdBusRequestNameError): ...


class SdBusRequestNameExistsError(SdBusRequestNameError): ...


class SdBusRequestNameInQueueError(SdBusRequestNameError): ...


class DbusClientError(DbusError): ...


class DbusMethodError(DbusError):

    error_name: str

    def __init__(self, message: str | None = None, *, name: str | None = None) -> None:
        if not hasattr(self, "error_name"):
            assert name is not None, "name= not provided"
        self.error_name = name or self.error_name
        self.error_message = message
        super().__init__(self.error_name)

    subclasses: ClassVar[Dict[str, Type[DbusMethodError]]] = {}

    @staticmethod
    def create(name: str, message: str | None = None):
        DbusMethodErrorSubclass = DbusMethodError.subclasses.get(name)
        if DbusMethodErrorSubclass is None:
            return DbusMethodError(name=name, message=message)
        else:
            return DbusMethodErrorSubclass(name=name, message=message)

    def __init_subclass__(cls, name: str) -> None:
        super().__init_subclass__()
        setattr(cls, "error_name", name)
        cls.subclasses[name] = cls


class DbusFailedError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.Failed",
): ...


class DbusNoMemoryError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.NoMemory",
): ...


class DbusServiceUnknownError(
    DbusMethodError, name="org.freedesktop.DBus.Error.ServiceUnknown"
): ...


class DbusNameHasNoOwnerError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.NameHasNoOwner",
): ...


class DbusNoReplyError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.NoReply",
): ...


class DbusIOError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.IOError",
): ...


class DbusBadAddressError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.BadAddress",
): ...


class DbusNotSupportedError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.NotSupported",
): ...


class DbusLimitsExceededError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.LimitsExceeded",
): ...


class DbusAccessDeniedError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.AccessDenied",
): ...


class DbusAuthFailedError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.AuthFailed",
): ...


class DbusNoServerError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.NoServer",
): ...


class DbusTimeoutError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.Timeout",
): ...


class DbusNoNetworkError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.NoNetwork",
): ...


class DbusAddressInUseError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.AddressInUse",
): ...


class DbusDisconnectedError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.Disconnected",
): ...


class DbusInvalidArgsError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.InvalidArgs",
): ...


class DbusFileNotFoundError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.FileNotFound",
): ...


class DbusFileExistsError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.FileExists",
): ...


class DbusUnknownMethodError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.UnknownMethod",
): ...


class DbusUnknownObjectError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.UnknownObject",
): ...


class DbusUnknownInterfaceError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.UnknownInterface",
): ...


class DbusUnknownPropertyError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.UnknownProperty",
): ...


class DbusPropertyReadOnlyError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.PropertyReadOnly",
): ...


class DbusUnixProcessIdUnknownError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.UnixProcessIdUnknown",
): ...


class DbusInvalidSignatureError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.InvalidSignature",
): ...


class DbusInvalidFileContentError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.InvalidFileContent",
): ...


class DbusInconsistentMessageError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.InconsistentMessage",
): ...


class DbusMatchRuleNotFound(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.MatchRuleNotFound",
): ...


class DbusMatchRuleInvalidError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error.MatchRuleInvalid",
): ...


class DbusInteractiveAuthorizationRequiredError(
    DbusMethodError,
    name="org.freedesktop.DBus.Error" ".InteractiveAuthorizationRequired",
): ...
