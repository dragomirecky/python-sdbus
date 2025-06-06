from __future__ import annotations

import weakref
from abc import ABC, abstractmethod
from contextlib import ExitStack
from typing import TYPE_CHECKING, Type

from _sdbus import is_member_name_valid
from aiodbus.bus import DbusInterfaceBuilder

if TYPE_CHECKING:
    from aiodbus.interface.base import DbusInterface


class DbusMember:
    interface_name: str
    serving_enabled: bool

    @property
    def name(self) -> str:
        try:
            return self._name
        except AttributeError:
            raise RuntimeError("Member name not set")

    @staticmethod
    def dbusify_name(name: str) -> str:
        """
        Convert Python variable name to D-Bus member name.
        snake_case -> PascalCase
        """
        if name.startswith("_"):
            name = name[1:]
        components = name.split("_")
        return "".join(x.capitalize() for x in components)

    @staticmethod
    def ensure_name_valid(name: str):
        try:
            assert is_member_name_valid(
                name
            ), f'Invalid name: "{name}"; {DbusMember.name_requirements}'
        except NotImplementedError:
            ...

    name_requirements = (
        "Member name must only contain ASCII characters, "
        "cannot start with digit, "
        "must not contain dot '.' and be between 1 "
        "and 255 characters in length."
    )

    def __init__(self, name: str | None) -> None:
        if name is not None:
            self._set_name(name)

    def __set_name__(self, owner: object, name: str) -> None:
        if not hasattr(owner, "_name"):
            name = self.dbusify_name(name)
            self._set_name(name)

    def _set_name(self, name: str) -> None:
        self.ensure_name_valid(name)
        self._name = name


class DbusClassMember[I: DbusInterface, M: DbusMember]:
    """
    Member bound to an interface class.
    """

    def __init__(self, local_object_cls: Type[I], member: M, **kwargs):
        self.__local_object_cls = local_object_cls
        self.__member = member
        self.__doc__ = member.__doc__
        super().__init__(**kwargs)

    @property
    def local_object_cls(self) -> Type[I]:
        return self.__local_object_cls

    @property
    def member(self) -> M:
        return self.__member


class DbusBoundMember[I: DbusInterface, M: DbusMember](ABC):
    """
    Member of an interface that has been bound to a local object or proxy to a remote object.
    """

    def __init__(self, local_object: I, member: M, **kwargs):
        self.__local_object_ref = weakref.ref(local_object)
        self.__member = member
        self.__doc__ = member.__doc__
        super().__init__(**kwargs)

    @property
    def local_object(self) -> I:
        local_object = self.__local_object_ref()
        if local_object is None:
            raise RuntimeError("Local object no longer exists")
        return local_object

    @property
    def member(self) -> M:
        return self.__member


class DbusLocalMember[I: DbusInterface, M: DbusMember](DbusBoundMember[I, M]):
    """
    Base class identifying members bound to local objects.
    """

    @abstractmethod
    def export_to_dbus(self, interface: DbusInterfaceBuilder, exit_stack: ExitStack) -> None: ...


class DbusProxyMember[I: DbusInterface, M: DbusMember](DbusBoundMember[I, M]):
    """
    Base class identifying members bound to remote objects.
    """

    ...
