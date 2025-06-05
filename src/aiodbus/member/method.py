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

import inspect
from abc import ABC, abstractmethod
from contextlib import ExitStack
from inspect import iscoroutinefunction
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Concatenate,
    List,
    Optional,
    Protocol,
    Sequence,
    Type,
    Union,
    Unpack,
    cast,
    overload,
    override,
)

from aiodbus.bus import DbusInterfaceBuilder, MethodFlags
from aiodbus.member.base import (
    DbusBoundMember,
    DbusClassMember,
    DbusLocalMember,
    DbusMember,
    DbusProxyMember,
)
from aiodbus.meta import DbusRemoteObjectMeta
from aiodbus.signature import MethodMapping

if TYPE_CHECKING:
    from aiodbus.basic_types import DbusCompleteType
    from aiodbus.interface.base import DbusInterface


type AnyAsyncMethod[**P, R] = Callable[Concatenate[Any, P], Awaitable[R]]


class AsyncFunction[**P, R](Protocol):
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...


class DbusMethodMiddleware[**P, R](Protocol):
    async def __call__(self, func: AsyncFunction[P, R], *args: P.args, **kwargs: P.kwargs) -> R: ...


class DbusMethod[**P, R](DbusMember):

    def __init__(
        self,
        name: Optional[str],
        input_signature: str | None,
        input_args_names: Sequence[str] | None,
        result_signature: str | None,
        result_args_names: Sequence[str] | None,
        unbound_method: AnyAsyncMethod[P, R],
        **flags: Unpack[MethodFlags],
    ):
        assert not isinstance(input_args_names, str), (
            "Passed a string as input args"
            " names. Did you forget to put"
            " it in to a tuple ('string', ) ?"
        )

        if name is None:
            name = DbusMethod.dbusify_name(unbound_method.__name__)

        super().__init__(name)
        self.unbound_method = unbound_method

        if (
            input_signature is not None
            or result_signature is not None
            or input_args_names is not None
            or result_args_names is not None
        ):
            self.mapping = MethodMapping.from_manual_input(
                input_signature=input_signature or "",
                input_names=input_args_names,
                result_signature=result_signature or "",
                result_names=result_args_names,
                callable=unbound_method,
            )
        else:
            self.mapping = MethodMapping.from_callable(unbound_method)

        self.method_name = name
        self.input_signature = self.mapping.input_conversion.signature
        self.result_signature = self.mapping.result_conversion.signature

        self.flags = flags

        self.to_dbus_middlewares: List[DbusMethodMiddleware] = []
        self.from_dbus_middlewares: List[DbusMethodMiddleware] = []

        self.__doc__ = unbound_method.__doc__

    @property
    def member_name(self) -> str:
        return self.method_name

    @overload
    def __get__[I: DbusInterface](
        self,
        obj: None,
        obj_class: Type[I],
    ) -> DbusClassMember[I, DbusMethod[P, R]]: ...

    @overload
    def __get__[I: DbusInterface](
        self,
        obj: I,
        obj_class: Type[I],
    ) -> DbusBoundMethod[I, P, R]: ...

    def __get__[I: DbusInterface](
        self,
        obj: Optional[I],
        obj_class: Optional[Type[I]] = None,
    ) -> Union[DbusBoundMethod[I, P, R], DbusClassMember[I, DbusMethod[P, R]]]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return DbusProxyMethod(member=self, local_object=obj, proxy_meta=dbus_meta)
            else:
                return DbusLocalMethod(member=self, local_object=obj)
        else:
            assert obj_class is not None
            return DbusClassMember(local_object_cls=obj_class, member=self)


class DbusBoundMethod[I: DbusInterface, **P, R](DbusBoundMember[I, DbusMethod[P, R]], ABC):
    @abstractmethod
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...


class DbusProxyMethod[I: DbusInterface, **P, R](DbusBoundMethod[I, P, R], DbusProxyMember):
    """
    Method bound to a remote dbus object.
    """

    def __init__(
        self,
        proxy_meta: DbusRemoteObjectMeta,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.proxy_meta = proxy_meta

    def _flatten_args(self, *args: P.args, **kwargs: P.kwargs) -> List[Any]:
        signature = inspect.signature(self.member.unbound_method)
        bound_args = signature.bind(None, *args, **kwargs)  # None for the first "self" arg
        bound_args.apply_defaults()
        return list(bound_args.arguments.values())[1:]  # drop "self" arg

    async def _make_dbus_call(self, *args: P.args, **kwargs: P.kwargs) -> R:
        bus = self.proxy_meta.attached_bus
        result = await bus.call_method(
            destination=self.proxy_meta.service_name,
            path=self.proxy_meta.object_path,
            interface=self.member.interface_name,
            member=self.member.method_name,
            signature=self.member.input_signature,
            args=self.member.mapping.input_conversion.to_dbus(self._flatten_args(*args, **kwargs)),
            no_reply=self.member.flags.get("no_reply", False),
        )
        return self.member.mapping.result_conversion.from_dbus(result)

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Call the method (over dbus).
        """
        return await call_with_middlewares(
            self._make_dbus_call,
            self.member.to_dbus_middlewares.copy(),
            *args,
            **kwargs,
        )


class DbusLocalMethod[I: DbusInterface, **P, R](DbusBoundMethod[I, P, R], DbusLocalMember):
    """
    Method bound to a local dbus object.
    """

    @override
    def export_to_dbus(self, interface: DbusInterfaceBuilder, exit_stack: ExitStack):
        interface.add_method(
            self.member.method_name,
            self.member.input_signature,
            tuple(p.name for p in self.member.mapping.input_params),
            self.member.result_signature,
            tuple(p.name for p in self.member.mapping.result_params),
            self._handle_dbus_call,
            **self.member.flags,
        )

    async def _handle_dbus_call(self, *args: DbusCompleteType):
        """
        Handle incoming dbus call to the method (from dbus).
        """
        bound_method = self.member.unbound_method.__get__(self.local_object, None)

        result = await call_with_middlewares(
            bound_method,
            self.member.from_dbus_middlewares.copy(),
            *self.member.mapping.input_conversion.from_dbus(args),
        )
        return self.member.mapping.result_conversion.to_dbus(result)

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Call the method (locally).
        """
        # no middlewares for local-only calls
        return await self.member.unbound_method(self.local_object, *args, **kwargs)


def dbus_method[**P, R](
    input_signature: str | None = None,
    result_signature: str | None = None,
    result_args_names: Sequence[str] | None = None,
    input_args_names: Sequence[str] | None = None,
    name: Optional[str] = None,
    **flags: Unpack[MethodFlags],
) -> Callable[[AnyAsyncMethod[P, R]], DbusMethod[P, R]]:

    def dbus_method_decorator(
        original_method: AnyAsyncMethod[P, R],
    ) -> DbusMethod[P, R]:
        assert iscoroutinefunction(original_method), (
            "Expected coroutine function. ",
            "Maybe you forgot 'async' keyword?",
        )
        new_wrapper = DbusMethod[P, R](
            unbound_method=original_method,
            name=name,
            input_signature=input_signature,
            result_signature=result_signature,
            result_args_names=result_args_names,
            input_args_names=input_args_names,
            **flags,
        )

        return new_wrapper

    return dbus_method_decorator


async def call_with_middlewares[**P, R](
    func: AsyncFunction[P, R],
    middlewares: List[DbusMethodMiddleware],
    *args: P.args,
    **kwargs: P.kwargs,
):
    if not middlewares:
        return await func(*args, **kwargs)
    else:
        middleware = middlewares.pop(-1)

        async def call_next(*args: P.args, **kwargs: P.kwargs) -> R:
            return await call_with_middlewares(func, middlewares, *args, **kwargs)

        return await middleware(call_next, *args, **kwargs)
