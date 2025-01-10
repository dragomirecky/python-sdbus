

from aiodbus.interface.base import DbusInterfaceBaseAsync
from aiodbus.member.method import dbus_method_async


class DbusPeerInterfaceAsync(
    DbusInterfaceBaseAsync,
    interface_name='org.freedesktop.DBus.Peer',
    serving_enabled=False,
):

    @dbus_method_async(method_name='Ping')
    async def dbus_ping(self) -> None:
        raise NotImplementedError

    @dbus_method_async(method_name='GetMachineId')
    async def dbus_machine_id(self) -> str:
        raise NotImplementedError
