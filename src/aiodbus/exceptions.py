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


class RequestNameError(DbusError): ...


class AlreadyOwner(RequestNameError): ...


class NameExistsError(RequestNameError): ...


class NameInQueueError(RequestNameError): ...


class DbusClientError(DbusError): ...


class MethodCallError(DbusError):

    error_name: str

    def __init__(self, message: str | None = None, *, name: str | None = None) -> None:
        if not hasattr(self, "error_name"):
            assert name is not None, "name= not provided"
        self.error_name = name or self.error_name
        self.error_message = message
        super().__init__(self.error_name)

    subclasses: ClassVar[Dict[str, Type[MethodCallError]]] = {}

    @staticmethod
    def create(name: str, message: str | None = None):
        DbusMethodErrorSubclass = MethodCallError.subclasses.get(name)
        if DbusMethodErrorSubclass is None:
            return MethodCallError(name=name, message=message)
        else:
            return DbusMethodErrorSubclass(name=name, message=message)

    def __init_subclass__(cls, name: str) -> None:
        super().__init_subclass__()
        setattr(cls, "error_name", name)
        cls.subclasses[name] = cls


class CallFailedError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.Failed",
): ...


class NoMemoryError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.NoMemory",
): ...


class ServiceUnknownError(MethodCallError, name="org.freedesktop.DBus.Error.ServiceUnknown"): ...


class NameHasNoOwnerError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.NameHasNoOwner",
): ...


class NoReplyError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.NoReply",
): ...


class IOError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.IOError",
): ...


class BadAddressError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.BadAddress",
): ...


class NotSupportedError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.NotSupported",
): ...


class LimitsExceededError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.LimitsExceeded",
): ...


class AccessDeniedError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.AccessDenied",
): ...


class AuthFailedError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.AuthFailed",
): ...


class NoServerError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.NoServer",
): ...


class TimeoutError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.Timeout",
): ...


class NoNetworkError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.NoNetwork",
): ...


class AddressInUseError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.AddressInUse",
): ...


class DisconnectedError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.Disconnected",
): ...


class InvalidArgsError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.InvalidArgs",
): ...


class FileNotFoundError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.FileNotFound",
): ...


class FileExistsError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.FileExists",
): ...


class UknownMethodError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.UnknownMethod",
): ...


class UnknownObjectError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.UnknownObject",
): ...


class UnknownInterfaceError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.UnknownInterface",
): ...


class UnknownPropertyError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.UnknownProperty",
): ...


class PropertyReadOnlyError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.PropertyReadOnly",
): ...


class UnixProcessIdUnknown(
    MethodCallError,
    name="org.freedesktop.DBus.Error.UnixProcessIdUnknown",
): ...


class InvalidSignatureError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.InvalidSignature",
): ...


class InvalidFileContentError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.InvalidFileContent",
): ...


class InconsistentMessageError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.InconsistentMessage",
): ...


class MatchRuleNotFoundError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.MatchRuleNotFound",
): ...


class MatchRuleInvalidError(
    MethodCallError,
    name="org.freedesktop.DBus.Error.MatchRuleInvalid",
): ...


class InteractiveAuthorizationRequiredError(
    MethodCallError,
    name="org.freedesktop.DBus.Error" ".InteractiveAuthorizationRequired",
): ...
