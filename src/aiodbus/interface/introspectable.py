from aiodbus.interface.base import DbusInterface
from aiodbus.member.method import dbus_method


class DbusIntrospectable(
    DbusInterface,
    interface_name="org.freedesktop.DBus.Introspectable",
    serving_enabled=False,
):

    @dbus_method(name="Introspect")
    async def dbus_introspect(self) -> str:
        raise NotImplementedError
