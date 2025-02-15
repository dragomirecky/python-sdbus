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

from abc import ABC, abstractmethod
from inspect import getfullargspec
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

from _sdbus import is_interface_name_valid, is_member_name_valid
from aiodbus.bus import Dbus, Interface, get_default_bus
from aiodbus.handle import DbusExportHandle
from aiodbus.member.base import DbusMember

if TYPE_CHECKING:
    from aiodbus.member.method import DbusMethodMiddleware

from .dbus_common_funcs import _is_property_flags_correct, _method_name_converter

SelfMeta = TypeVar("SelfMeta", bound="DbusInterfaceMetaCommon")


T = TypeVar("T")


class DbusInterfaceMetaCommon(type):
    def __new__(
        cls: Type[SelfMeta],
        name: str,
        bases: Tuple[type, ...],
        namespace: Dict[str, Any],
        interface_name: Optional[str] = None,
        serving_enabled: bool = True,
    ) -> SelfMeta:
        if interface_name is not None:
            try:
                assert is_interface_name_valid(interface_name), (
                    f'Invalid interface name: "{interface_name}"; '
                    "Interface names must be composed of 2 or more elements "
                    "separated by a dot '.' character. All elements must "
                    "contain at least one character, consist of ASCII "
                    "characters, first character must not be digit and "
                    "length must not exceed 255 characters."
                )
            except NotImplementedError:
                ...

        for attr_name, attr in namespace.items():
            if not isinstance(attr, DbusMember):
                continue

            # TODO: Fix async metaclass copying all methods
            if hasattr(attr, "interface_name"):
                continue

            if interface_name is None:
                raise TypeError(
                    f"Defined D-Bus element {attr_name!r} without "
                    f"interface name in the class {name!r}."
                )

            attr.interface_name = interface_name
            attr.serving_enabled = serving_enabled

        new_cls = super().__new__(cls, name, bases, namespace)

        return new_cls


MEMBER_NAME_REQUIREMENTS = (
    "Member name must only contain ASCII characters, "
    "cannot start with digit, "
    "must not contain dot '.' and be between 1 "
    "and 255 characters in length."
)


class DbusPropertyCommon(DbusMember):
    def __init__(
        self,
        property_name: Optional[str],
        property_signature: str,
        flags: int,
        original_method: FunctionType,
    ):
        if property_name is None:
            property_name = "".join(_method_name_converter(original_method.__name__))

        assert _is_property_flags_correct(flags), (
            "Incorrect number of Property flags. "
            "Only one of DbusPropertyConstFlag, DbusPropertyEmitsChangeFlag, "
            "DbusPropertyEmitsInvalidationFlag or DbusPropertyExplicitFlag "
            "is allowed."
        )

        super().__init__(property_name)
        self.property_name: str = property_name
        self.property_signature = property_signature
        self.flags = flags

    @property
    def member_name(self) -> str:
        return self.property_name


class DbusSignalCommon(DbusMember):
    def __init__(
        self,
        signal_name: Optional[str],
        signal_signature: str,
        args_names: Sequence[str],
        flags: int,
        original_method: FunctionType,
    ):
        if signal_name is None:
            signal_name = "".join(_method_name_converter(original_method.__name__))

        super().__init__(signal_name)
        self.signal_name = signal_name
        self.signal_signature = signal_signature
        self.args_names = args_names
        self.flags = flags

        self.__doc__ = original_method.__doc__
        self.__annotations__ = original_method.__annotations__

    @property
    def member_name(self) -> str:
        return self.signal_name


class DbusBoundMember(ABC):
    @property
    @abstractmethod
    def member(self) -> DbusMember: ...


class DbusLocalMember(DbusBoundMember):
    @abstractmethod
    def _append_to_interface(
        self,
        interface: Interface,
        handle: DbusExportHandle,
    ) -> None: ...


class DbusProxyMember(DbusBoundMember): ...


class DbusMethodOverride(Generic[T]):
    def __init__(self, override_method: T):
        self.override_method = override_method


class DbusPropertyOverride(Generic[T]):
    def __init__(self, getter_override: Callable[[Any], T]):
        self.getter_override = getter_override
        self.setter_override: Optional[Callable[[Any, T], None]] = None
        self.is_setter_public = True

    def setter(self, new_setter: Optional[Callable[[Any, T], None]]) -> None:
        self.setter_override = new_setter

    def setter_private(
        self,
        new_setter: Optional[Callable[[Any, T], None]],
    ) -> None:
        self.setter_override = new_setter
        self.is_setter_public = False


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
