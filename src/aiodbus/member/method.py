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
from inspect import getfullargspec, iscoroutinefunction
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
)

from aiodbus.bus import DbusInterfaceBuilder, MethodFlags
from aiodbus.member.base import (
    DbusBoundMember,
    DbusLocalMember,
    DbusMember,
    DbusProxyMember,
)
from aiodbus.meta import DbusRemoteObjectMeta

if TYPE_CHECKING:
    from _sdbus import DbusCompleteType
    from aiodbus.interface.base import DbusExportHandle, DbusInterface


type AnyAsyncMethod[**P, R] = Callable[Concatenate[Any, P], Awaitable[R]]


class AsyncFunction[**P, R](Protocol):
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...


class DbusMethodMiddleware[**P, R](Protocol):
    async def __call__(self, func: AsyncFunction[P, R], *args: P.args, **kwargs: P.kwargs) -> R: ...


class DbusMethod[**P, R](DbusMember):

    def __init__(
        self,
        name: Optional[str],
        input_signature: str,
        input_args_names: Optional[Sequence[str]],
        result_signature: str,
        result_args_names: Optional[Sequence[str]],
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
        self.args_spec = getfullargspec(unbound_method)
        self.args_names = self.args_spec.args[1:]  # 1: because of self

        self.method_name = name
        self.input_signature = input_signature
        self.input_args_names: Sequence[str] = ()
        if input_args_names is not None:
            assert not any(" " in x for x in input_args_names), (
                "Can't have spaces in argument input names" f"Args: {input_args_names}"
            )

            self.input_args_names = input_args_names
        elif result_args_names is not None:
            self.input_args_names = self.args_names

        self.result_signature = result_signature
        self.result_args_names: Sequence[str] = ()
        if result_args_names is not None:
            assert not any(" " in x for x in result_args_names), (
                "Can't have spaces in argument result names." f"Args: {result_args_names}"
            )

            self.result_args_names = result_args_names

        self.flags = flags

        self.to_dbus_middlewares: List[DbusMethodMiddleware] = []
        self.from_dbus_middlewares: List[DbusMethodMiddleware] = []

        self.__doc__ = unbound_method.__doc__

    @property
    def member_name(self) -> str:
        return self.method_name

    @overload
    def __get__(
        self,
        obj: None,
        obj_class: Type[DbusInterface],
    ) -> DbusMethod[P, R]: ...

    @overload
    def __get__(
        self,
        obj: DbusInterface,
        obj_class: Type[DbusInterface],
    ) -> DbusBoundMethod[P, R]: ...

    def __get__(
        self,
        obj: Optional[DbusInterface],
        obj_class: Optional[Type[DbusInterface]] = None,
    ) -> Union[DbusBoundMethod[P, R], DbusMethod[P, R]]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return DbusProxyMethod(self, dbus_meta)
            else:
                return DbusLocalMethod(self, obj)
        else:
            return self


class DbusBoundMethod[**P, R](DbusBoundMember, ABC):
    def __init__(self, dbus_method: DbusMethod[P, R], **kwargs):
        super().__init__(**kwargs)
        self.dbus_method = dbus_method

    @property
    def member(self) -> DbusMember:
        return self.dbus_method

    @abstractmethod
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...


class DbusProxyMethod[**P, R](DbusBoundMethod[P, R], DbusProxyMember):
    """
    Method bound to a remote dbus object.
    """

    def __init__(
        self,
        dbus_method: DbusMethod[P, R],
        proxy_meta: DbusRemoteObjectMeta,
    ):
        super().__init__(dbus_method)
        self.proxy_meta = proxy_meta
        self.__doc__ = dbus_method.__doc__

    def _flatten_args(self, *args: P.args, **kwargs: P.kwargs) -> List[Any]:
        signature = inspect.signature(self.dbus_method.unbound_method)
        bound_args = signature.bind(None, *args, **kwargs)  # None for the first "self" arg
        bound_args.apply_defaults()
        return list(bound_args.arguments.values())[1:]  # drop "self" arg

    async def _make_dbus_call(self, *args: P.args, **kwargs: P.kwargs) -> R:
        bus = self.proxy_meta.attached_bus
        result = await bus.call_method(
            destination=self.proxy_meta.service_name,
            path=self.proxy_meta.object_path,
            interface=self.dbus_method.interface_name,
            member=self.dbus_method.method_name,
            signature=self.dbus_method.input_signature,
            args=self._flatten_args(*args, **kwargs),
            no_reply=self.dbus_method.flags.get("no_reply", False),
        )
        return cast(R, result)  # we have to hope it's correct

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Call the method (over dbus).
        """
        return await call_with_middlewares(
            self._make_dbus_call,
            self.dbus_method.to_dbus_middlewares.copy(),
            *args,
            **kwargs,
        )


class DbusLocalMethod[**P, R](DbusBoundMethod[P, R], DbusLocalMember):
    """
    Method bound to a local dbus object.
    """

    def __init__(
        self,
        dbus_method: DbusMethod[P, R],
        local_object: DbusInterface,
    ):
        super().__init__(dbus_method=dbus_method, local_object=local_object)
        self.__doc__ = dbus_method.__doc__

    def _append_to_interface(self, interface: DbusInterfaceBuilder, handle: DbusExportHandle):
        interface.add_method(
            self.dbus_method.method_name,
            self.dbus_method.input_signature,
            self.dbus_method.input_args_names,
            self.dbus_method.result_signature,
            self.dbus_method.result_args_names,
            self._handle_dbus_call,
            **self.dbus_method.flags,
        )

    async def _handle_dbus_call(self, *args: DbusCompleteType):
        """
        Handle incoming dbus call to the method (from dbus).
        """
        bound_method = self.dbus_method.unbound_method.__get__(self.local_object, None)

        return await call_with_middlewares(
            bound_method,
            self.dbus_method.from_dbus_middlewares.copy(),
            *args,  # type: ignore
        )

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Call the method (locally).
        """
        # no middlewares for local-only calls
        return await self.dbus_method.unbound_method(self.local_object, *args, **kwargs)


def dbus_method[**P, R](
    input_signature: str = "",
    result_signature: str = "",
    result_args_names: Optional[Sequence[str]] = None,
    input_args_names: Optional[Sequence[str]] = None,
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
