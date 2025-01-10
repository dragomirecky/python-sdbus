from aiodbus.interface.base import DbusInterfaceBase
from aiodbus.member.method import dbus_method


class DbusPeerInterfaceAsync(
    DbusInterfaceBase,
    interface_name="org.freedesktop.DBus.Peer",
    serving_enabled=False,
):

    @dbus_method(method_name="Ping")
    async def dbus_ping(self) -> None:
        raise NotImplementedError

    @dbus_method(method_name="GetMachineId")
    async def dbus_machine_id(self) -> str:
        raise NotImplementedError
