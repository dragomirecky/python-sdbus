from typing import Any, Dict, List, Literal, Tuple

from aiodbus.dbus_common_funcs import _parse_properties_vardict
from aiodbus.interface.base import DbusInterfaceBase
from aiodbus.member.method import dbus_method
from aiodbus.member.signal import dbus_signal

DBUS_PROPERTIES_CHANGED_TYPING = Tuple[
    str,
    Dict[str, Tuple[str, Any]],
    List[str],
]


class DbusPropertiesInterfaceAsync(
    DbusInterfaceBase,
    interface_name="org.freedesktop.DBus.Properties",
    serving_enabled=False,
):

    @dbus_signal("sa{sv}as")
    def properties_changed(self) -> DBUS_PROPERTIES_CHANGED_TYPING:
        raise NotImplementedError

    @dbus_method("s", "a{sv}", name="GetAll")
    async def _properties_get_all(self, interface_name: str) -> Dict[str, Tuple[str, Any]]:
        raise NotImplementedError

    async def properties_get_all_dict(
        self,
        on_unknown_member: Literal["error", "ignore", "reuse"] = "error",
    ) -> Dict[str, Any]:

        properties: Dict[str, Any] = {}

        for interface_name, meta in self._dbus_iter_interfaces_meta():
            if not meta.serving_enabled:
                continue

            dbus_properties_data = await self._properties_get_all(interface_name)

            properties.update(
                _parse_properties_vardict(
                    meta.dbus_member_to_python_attr,
                    dbus_properties_data,
                    on_unknown_member,
                )
            )

        return properties
