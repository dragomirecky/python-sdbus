from typing import Any, Dict, List, Literal, Mapping, Tuple

from aiodbus.interface.base import DbusInterface
from aiodbus.member.method import dbus_method
from aiodbus.member.signal import DbusSignal

DBUS_PROPERTIES_CHANGED_TYPING = Tuple[
    str,
    Dict[str, Tuple[str, Any]],
    List[str],
]


class DbusPropertiesInterface(
    DbusInterface,
    interface_name="org.freedesktop.DBus.Properties",
    serving_enabled=False,
):
    properties_changed = DbusSignal[DBUS_PROPERTIES_CHANGED_TYPING](signature="sa{sv}as")

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


def _parse_properties_vardict(
    properties_name_map: Mapping[str, str],
    properties_vardict: Dict[str, Tuple[str, Any]],
    on_unknown_member: Literal["error", "ignore", "reuse"],
) -> Dict[str, Any]:

    properties_translated: Dict[str, Any] = {}

    for member_name, variant in properties_vardict.items():
        try:
            python_name = properties_name_map[member_name]
        except KeyError:
            if on_unknown_member == "error":
                raise
            elif on_unknown_member == "ignore":
                continue
            elif on_unknown_member == "reuse":
                python_name = member_name
            else:
                raise ValueError

        properties_translated[python_name] = variant[1]

    return properties_translated
