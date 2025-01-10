from aiodbus.interface.base import DbusInterfaceBase
from aiodbus.member.method import dbus_method


class DbusIntrospectableAsync(
    DbusInterfaceBase,
    interface_name="org.freedesktop.DBus.Introspectable",
    serving_enabled=False,
):

    @dbus_method(method_name="Introspect")
    async def dbus_introspect(self) -> str:
        raise NotImplementedError
