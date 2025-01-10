

from aiodbus.interface.base import DbusInterfaceBaseAsync
from aiodbus.member.method import dbus_method_async


class DbusIntrospectableAsync(
    DbusInterfaceBaseAsync,
    interface_name='org.freedesktop.DBus.Introspectable',
    serving_enabled=False,
):

    @dbus_method_async(method_name='Introspect')
    async def dbus_introspect(self) -> str:
        raise NotImplementedError


