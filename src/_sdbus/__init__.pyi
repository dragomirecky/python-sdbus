# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020-2023 igo95862
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

from asyncio import Future
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

DbusBasicType = Union[str, int, bytes, float, Any]
DbusStructType = Tuple[DbusBasicType, ...]
DbusDictType = Dict[DbusBasicType, DbusBasicType]
DbusVariantType = Tuple[str, DbusStructType]
DbusArrayType = List[DbusBasicType]
DbusCompleteType = Union[
    DbusBasicType, DbusStructType, DbusDictType, DbusVariantType, DbusArrayType
]
DbusCompleteTypes = Tuple[DbusCompleteType, ...]

class SdBusSlot:
    """Holds reference to SdBus slot"""

    def close(self) -> None: ...

class SdBusInterface:
    slot: Optional[SdBusSlot]
    method_list: List[object]
    method_dict: Dict[bytes, object]
    property_list: List[object]
    property_get_dict: Dict[bytes, object]
    property_set_dict: Dict[bytes, object]
    signal_list: List[object]

    def add_method(
        self,
        member_name: str,
        signature: str,
        input_args_names: Sequence[str],
        result_signature: str,
        result_args_names: Sequence[str],
        flags: int,
        callback: Callable[[SdBusMessage], Coroutine[Any, Any, None]],
        /,
    ) -> None: ...
    def add_property(
        self,
        property_name: str,
        property_signature: str,
        get_function: Callable[[SdBusMessage], Any],
        set_function: Optional[Callable[[SdBusMessage], None]],
        flags: int,
        /,
    ) -> None: ...
    def add_signal(
        self,
        signal_name: str,
        signal_signature: str,
        signal_args_names: Sequence[str],
        flags: int,
        /,
    ) -> None: ...

class SdBusMessage:
    def append_data(self, signature: str, *args: DbusCompleteType) -> None: ...
    def open_container(self, container_type: str, container_signature: str, /) -> None: ...
    def close_container(self) -> None: ...
    def enter_container(self, container_type: str, container_signature: str, /) -> None: ...
    def exit_container(self) -> None: ...
    def dump(self) -> None: ...
    def seal(self) -> None: ...
    def get_contents(self) -> Tuple[DbusCompleteType, ...]: ...
    def create_reply(self) -> SdBusMessage: ...
    def create_error_reply(self, error_name: str, error_message: str, /) -> SdBusMessage: ...
    def send(self) -> None: ...
    def parse_to_tuple(self) -> Tuple[Any, ...]: ...
    def get_type(self) -> int: ...
    def get_error(self) -> Optional[Tuple[str, Optional[str]]]: ...

    expect_reply: bool = False
    destination: Optional[str] = None
    path: Optional[str] = None
    interface: Optional[str] = None
    member: Optional[str] = None
    sender: Optional[str] = None

class _SdBus:
    def call_async(self, message: SdBusMessage, /) -> Future[SdBusMessage]: ...
    def process(self) -> None: ...
    def get_fd(self) -> int: ...
    def new_method_call_message(
        self, destination_name: str, object_path: str, interface_name: str, member_name: str, /
    ) -> SdBusMessage: ...
    def new_property_get_message(
        self,
        destination_service_name: str,
        object_path: str,
        interface_name: str,
        member_name: str,
        /,
    ) -> SdBusMessage: ...
    def new_property_set_message(
        self,
        destination_service_name: str,
        object_path: str,
        interface_name: str,
        member_name: str,
        /,
    ) -> SdBusMessage: ...
    def new_signal_message(
        self, object_path: str, interface_name: str, member_name: str, /
    ) -> SdBusMessage: ...
    def add_interface(
        self, new_interface: SdBusInterface, object_path: str, interface_name: str, /
    ) -> None: ...
    def match_signal_async(
        self,
        senders_name: Optional[str],
        object_path: Optional[str],
        interface_name: Optional[str],
        member_name: Optional[str],
        callback: Callable[[SdBusMessage], None],
        /,
    ) -> Future[SdBusSlot]: ...
    def request_name(self, name: str, flags: int, /) -> Future[SdBusMessage]: ...
    def add_object_manager(self, path: str, /) -> SdBusSlot: ...
    def emit_object_added(self, path: str, /) -> None: ...
    def emit_object_removed(self, path: str, /) -> None: ...
    def close(self) -> None: ...
    def start(self) -> None: ...

    address: Optional[str] = None
    method_call_timeout_usec: int = 0

def sd_bus_open() -> _SdBus: ...
def sd_bus_open_user() -> _SdBus: ...
def sd_bus_open_system() -> _SdBus: ...
def sd_bus_open_system_remote(host: str, /) -> _SdBus: ...
def sd_bus_open_user_machine(machine: str, /) -> _SdBus: ...
def sd_bus_open_system_machine(machine: str, /) -> _SdBus: ...
def encode_object_path(prefix: str, external: str) -> str: ...
def decode_object_path(prefix: str, full_path: str) -> str: ...
def is_interface_name_valid(string_to_check: str, /) -> bool: ...
def is_service_name_valid(string_to_check: str, /) -> bool: ...
def is_member_name_valid(string_to_check: str, /) -> bool: ...
def is_object_path_valid(string_to_check: str, /) -> bool: ...

class SdBusError(Exception): ...

class SdBusMethodError(SdBusError):
    response: SdBusMessage

DbusDeprecatedFlag: int
DbusHiddenFlag: int
DbusUnprivilegedFlag: int
DbusNoReplyFlag: int
DbusPropertyConstFlag: int
DbusPropertyEmitsChangeFlag: int
DbusPropertyEmitsInvalidationFlag: int
DbusPropertyExplicitFlag: int
DbusSensitiveFlag: int

DbusMessageTypeMethodCall: int
DbusMessageTypeMethodReturn: int
DbusMessageTypeMethodError: int
DbusMessageTypeSignal: int

NameAllowReplacementFlag: int
NameReplaceExistingFlag: int
NameQueueFlag: int
