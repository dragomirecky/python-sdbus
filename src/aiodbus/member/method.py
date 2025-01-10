# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020-2023 igo95862

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
from __future__ import annotations
from contextvars import ContextVar, copy_context
from inspect import iscoroutinefunction
import logging
from types import FunctionType
from typing import Any, Awaitable, Callable, List, TYPE_CHECKING, cast, overload
from typing import Optional, Sequence, Type, TypeVar, Union
from weakref import ref as weak_ref

from _sdbus import DbusNoReplyFlag, SdBusInterface
from _sdbus import SdBusMessage
from aiodbus.dbus_common_elements import (
    DbusBoundMember,
    DbusLocalMember,
    DbusMember,
    DbusMethodCommon,
    DbusMethodOverride,
    DbusProxyMember,
    DbusRemoteObjectMeta,
)
from aiodbus.dbus_exceptions import DbusFailedError

if TYPE_CHECKING:
    from aiodbus.interface.base import DbusExportHandle, DbusInterfaceBase

T = TypeVar('T')

CURRENT_MESSAGE: ContextVar[SdBusMessage] = ContextVar('CURRENT_MESSAGE')


def get_current_message() -> SdBusMessage:
    return CURRENT_MESSAGE.get()


AnyAsyncFunc = Callable[..., Awaitable[Any]]
DbusMethodMiddleware = Callable[[AnyAsyncFunc], Awaitable[Any]]


async def call_with_middlewares(func: AnyAsyncFunc, args, kwargs, *, middlewares: List[DbusMethodMiddleware]):
    if not middlewares:
        return await func(*args, **kwargs)
    else:
        middleware = middlewares.pop(-1)

        async def call_next(*args, **kwargs):
            return await call_with_middlewares(func, args, kwargs, middlewares=middlewares)

        return await middleware(call_next, *args, **kwargs)

class DbusMethod(DbusMethodCommon, DbusMember):

    @overload
    def __get__(
        self,
        obj: None,
        obj_class: Type[DbusInterfaceBase],
    ) -> DbusMethod:
        ...

    @overload
    def __get__(
        self,
        obj: DbusInterfaceBase,
        obj_class: Type[DbusInterfaceBase],
    ) -> Callable[..., Any]:
        ...

    def __get__(
        self,
        obj: Optional[DbusInterfaceBase],
        obj_class: Optional[Type[DbusInterfaceBase]] = None,
    ) -> Union[Callable[..., Any], DbusMethod]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return DbusProxyMethod(self, dbus_meta)
            else:
                return DbusLocalMethod(self, obj)
        else:
            return self


class DbusBoundMethodBase(DbusBoundMember):
    def __init__(self, dbus_method: DbusMethod) -> None:
        self.dbus_method = dbus_method

    @property
    def member(self) -> DbusMember:
        return self.dbus_method

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


class DbusProxyMethod(DbusBoundMethodBase, DbusProxyMember):
    def __init__(
        self,
        dbus_method: DbusMethod,
        proxy_meta: DbusRemoteObjectMeta,
    ):
        super().__init__(dbus_method)
        self.proxy_meta = proxy_meta

        self.__doc__ = dbus_method.__doc__

    async def _dbus_call(self, call_message: SdBusMessage) -> Any:
        bus = self.proxy_meta.attached_bus
        reply_message = await bus.call_async(call_message)
        return reply_message.get_contents()

    @staticmethod
    async def _no_reply() -> None:
        return None

    async def _make_dbus_call(self, *args: Any, **kwargs: Any) -> Any:
        bus = self.proxy_meta.attached_bus
        dbus_method = self.dbus_method

        new_call_message = bus.new_method_call_message(
            self.proxy_meta.service_name,
            self.proxy_meta.object_path,
            dbus_method.interface_name,
            dbus_method.method_name,
        )

        if len(args) == dbus_method.num_of_args:
            assert not kwargs, (
                "Passed more arguments than method supports"
                f"Extra args: {kwargs}")
            rebuilt_args: Sequence[Any] = args
        else:
            rebuilt_args = dbus_method._rebuild_args(
                dbus_method.original_method,
                *args,
                **kwargs)

        if rebuilt_args:
            new_call_message.append_data(
                dbus_method.input_signature, *rebuilt_args)

        if dbus_method.flags & DbusNoReplyFlag:
            new_call_message.expect_reply = False
            new_call_message.send()
            return await self._no_reply()

        return await self._dbus_call(new_call_message)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return call_with_middlewares(self._make_dbus_call, args, kwargs, middlewares=self.dbus_method.to_dbus_middlewares.copy())


class DbusLocalMethod(DbusBoundMethodBase, DbusLocalMember):
    def __init__(
        self,
        dbus_method: DbusMethod,
        local_object: DbusInterfaceBase,
    ):
        super().__init__(dbus_method)
        self.local_object_ref = weak_ref(local_object)

        self.__doc__ = dbus_method.__doc__

    def _append_to_interface(
        self,
        interface: SdBusInterface,
        handle: DbusExportHandle,
    ) -> None:
        interface.add_method(
            self.dbus_method.method_name,
            self.dbus_method.input_signature,
            self.dbus_method.input_args_names,
            self.dbus_method.result_signature,
            self.dbus_method.result_args_names,
            self.dbus_method.flags,
            self._dbus_reply_call,
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        local_object = self.local_object_ref()
        if local_object is None:
            raise RuntimeError("Local object no longer exists!")

        # no middlewares for local-only calls
        return self.dbus_method.original_method(local_object, *args, **kwargs)

    async def _dbus_reply_call_method(
        self,
        request_message: SdBusMessage,
        local_object: DbusInterfaceBase,
    ) -> Any:

        local_method = self.dbus_method.original_method.__get__(
            local_object, None)

        CURRENT_MESSAGE.set(request_message)

        # apply from_dbus middlewares
        return await call_with_middlewares(local_method, request_message.parse_to_tuple(), {}, middlewares=self.dbus_method.from_dbus_middlewares.copy())

    async def _dbus_reply_call(
        self,
        request_message: SdBusMessage
    ) -> None:
        local_object = self.local_object_ref()
        if local_object is None:
            raise RuntimeError("Local object no longer exists!")

        call_context = copy_context()

        try:
            reply_data = await call_context.run(
                self._dbus_reply_call_method,
                request_message,
                local_object,
            )
        except DbusFailedError as e:
            if not request_message.expect_reply:
                return

            error_message = request_message.create_error_reply(
                e.dbus_error_name,
                str(e.args[0]) if e.args else "",
            )
            error_message.send()
            return
        except Exception:
            logger = logging.getLogger(__name__)
            logger.exception("Exception when handling a method call")
            error_message = request_message.create_error_reply(
                DbusFailedError.dbus_error_name,
                "",
            )
            error_message.send()
            return

        if not request_message.expect_reply:
            return

        reply_message = request_message.create_reply()

        if isinstance(reply_data, tuple):
            try:
                reply_message.append_data(
                    self.dbus_method.result_signature, *reply_data)
            except TypeError:
                # In case of single struct result type
                # We can't figure out if return is multiple values
                # or a tuple
                reply_message.append_data(
                    self.dbus_method.result_signature, reply_data)
        elif reply_data is not None:
            reply_message.append_data(
                self.dbus_method.result_signature, reply_data)

        reply_message.send()



def dbus_method(
    input_signature: str = "",
    result_signature: str = "",
    flags: int = 0,
    result_args_names: Optional[Sequence[str]] = None,
    input_args_names: Optional[Sequence[str]] = None,
    method_name: Optional[str] = None,
) -> Callable[[Any], DbusMethod]:

    assert not isinstance(input_signature, FunctionType), (
        "Passed function to decorator directly. "
        "Did you forget () round brackets?"
    )

    def dbus_method_decorator(original_method: T) -> T:
        assert isinstance(original_method, FunctionType)
        assert iscoroutinefunction(original_method), (
            "Expected coroutine function. ",
            "Maybe you forgot 'async' keyword?",
        )
        new_wrapper = DbusMethod(
            original_method=original_method,
            method_name=method_name,
            input_signature=input_signature,
            result_signature=result_signature,
            result_args_names=result_args_names,
            input_args_names=input_args_names,
            flags=flags,
        )

        return cast(T, new_wrapper)

    return dbus_method_decorator


def dbus_method_override() -> Callable[[T], T]:

    def new_decorator(
            new_function: T) -> T:
        return cast(T, DbusMethodOverride(new_function))

    return new_decorator
