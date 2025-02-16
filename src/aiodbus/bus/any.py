from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypedDict,
    Unpack,
)

from aiodbus.bus.message import DbusMessage
from aiodbus.handle import Closeable

if TYPE_CHECKING:
    from _sdbus import DbusCompleteType, DbusCompleteTypes


class MemberFlags(TypedDict, total=False):
    deprecated: bool
    hidden: bool
    unprivileged: bool


class MethodFlags(MemberFlags, total=False):
    no_reply: bool


class PropertyFlags(MemberFlags, total=False):
    explicit: bool
    emits_change: bool
    emits_invalidation: bool
    const: bool


class MethodCallable(Protocol):
    async def __call__(self, *args: DbusCompleteType) -> Any: ...


class DbusInterfaceBuilder(Protocol):
    def add_method(
        self,
        name: str,
        signature: str,
        input_args_names: Sequence[str],
        result_signature: str,
        result_args_names: Sequence[str],
        callback: MethodCallable,
        **flags: Unpack[MethodFlags],
    ) -> None:
        """Add a method member to this interface."""
        ...

    def add_property(
        self,
        name: str,
        signature: str,
        get_function: Callable[[], DbusCompleteTypes],
        set_function: Optional[Callable[[DbusCompleteTypes], None]],
        **flags: Unpack[PropertyFlags],
    ) -> None:
        """Add a property member to this interface."""
        ...

    def add_signal(
        self,
        name: str,
        signature: str,
        args_names: Sequence[str],
        **flags: Unpack[MemberFlags],
    ) -> None:
        """Add a signal member to this interface."""
        ...


class Dbus(Protocol):
    @property
    def address(self) -> Optional[str]: ...

    async def request_name(
        self,
        name: str,
        *,
        queue: bool = False,
        allow_replacement: bool = False,
        replace_existing: bool = False,
    ) -> None: ...

    async def call_method(
        self,
        *,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str,
        args: Iterable[DbusCompleteType],
        no_reply: bool = False,
    ) -> Tuple[DbusCompleteType, ...]:
        """
        Call a method on the dbus and return the result.
        """
        ...

    async def get_property(
        self,
        *,
        destination: str,
        path: str,
        interface: str,
        member: str,
    ) -> Tuple[DbusCompleteType, ...]: ...

    async def set_property(
        self,
        *,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str,
        args: Iterable[DbusCompleteType],
    ) -> None: ...

    def emit_signal(
        self,
        path: str,
        interface: str,
        member: str,
        signature: str,
        args: Iterable[DbusCompleteType],
    ): ...

    async def subscribe_signals(
        self,
        *,
        sender_filter: Optional[str] = None,
        path_filter: Optional[str] = None,
        interface_filter: Optional[str] = None,
        member_filter: Optional[str] = None,
        callback: Callable[[DbusMessage], None],
    ) -> Closeable: ...

    def create_interface(self) -> DbusInterfaceBuilder:
        """
        Create a new interface for this bus.

        The interface should be filled with members with the `add_*` methods.
        and exported with the published to the dbus with the `export` method.
        """
        ...

    def export(self, path: str, name: str, interface: DbusInterfaceBuilder) -> Closeable:
        """
        Publish an interface to the dbus.
        """
        ...

    def close(self) -> None:
        """
        Close connection to the dbus.
        """
        ...

    def __enter__(self) -> "Dbus": ...

    def __exit__(self, *_) -> None: ...
