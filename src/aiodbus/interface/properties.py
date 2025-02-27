from __future__ import annotations

import logging
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import (
    Any,
    ContextManager,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Type,
    Union,
    overload,
    override,
)

from aiodbus.interface.base import DbusInterface
from aiodbus.member.method import dbus_method
from aiodbus.member.property import DbusBoundProperty, DbusLocalProperty
from aiodbus.member.signal import (
    DbusBoundSignal,
    DbusLocalSignal,
    DbusProxySignal,
    DbusSignal,
)
from aiodbus.meta import DbusRemoteObjectMeta

DBUS_PROPERTIES_CHANGED_TYPING = Tuple[
    str,
    Dict[str, Tuple[str, Any]],
    List[str],
]

logger = logging.getLogger(__name__)


class PropertiesChangedSignal(DbusSignal[DBUS_PROPERTIES_CHANGED_TYPING]):
    @overload
    def __get__(
        self,
        obj: None,
        obj_class: Type[DbusInterface],
    ) -> PropertiesChangedSignal: ...

    @overload
    def __get__(
        self,
        obj: DbusInterface,
        obj_class: Type[DbusInterface],
    ) -> BoundPropertiesChangedSignal: ...

    def __get__(
        self,
        obj: Optional[DbusInterface],
        obj_class: Optional[Type[DbusInterface]] = None,
    ) -> Union[BoundPropertiesChangedSignal, PropertiesChangedSignal]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return ProxyPropertiesChangedSignal(self, dbus_meta)
            else:
                return LocalPropertiesChangedSignal(self, obj, dbus_meta)
        else:
            return self


class BoundPropertiesChangedSignal(DbusBoundSignal[DBUS_PROPERTIES_CHANGED_TYPING]):
    def emit_property_changed(self, prop: DbusBoundProperty):
        raise NotImplementedError

    def grouped_changes(self) -> ContextManager[None]:
        raise NotImplementedError


class LocalPropertiesChangedSignal(
    BoundPropertiesChangedSignal, DbusLocalSignal[DBUS_PROPERTIES_CHANGED_TYPING]
):
    def emit_properties_changed_to_callbacks(self, changes: set[DbusBoundProperty]):
        if not self.dbus_signal.local_callbacks:
            return

        for prop in changes:
            assert isinstance(prop, DbusLocalProperty)
            value = prop._get_value()
            signal_value: DBUS_PROPERTIES_CHANGED_TYPING = (
                prop.dbus_property.interface_name,
                {
                    prop.dbus_property.name: (
                        prop.dbus_property.signature,
                        value,
                    ),
                },
                [],
            )

            for callback in self.dbus_signal.local_callbacks:
                try:
                    callback(signal_value)
                except Exception:
                    logger.exception("Error in properties changed signal callback")

    @override
    def emit_property_changed(self, prop: DbusBoundProperty):
        dbus = self.local_meta.attached_bus
        path = self.local_meta.serving_object_path
        if dbus is None or path is None:
            return

        try:
            changes = self._pending_grouped_changes.get()
            changes[prop.dbus_property.interface_name].add(prop)
        except LookupError:
            dbus.emit_properties_changed(
                path=path,
                interface=prop.dbus_property.interface_name,
                properties=[prop.dbus_property.name],
            )
            self.emit_properties_changed_to_callbacks({prop})

    _pending_grouped_changes = ContextVar[dict[str, set[DbusBoundProperty]]](
        "pending_property_changes"
    )

    @override
    @contextmanager
    def grouped_changes(self):
        changes = defaultdict[str, set[DbusBoundProperty]](set)
        token = self._pending_grouped_changes.set(changes)
        try:
            yield
        finally:
            self._pending_grouped_changes.reset(token)
            bus, path = self.local_meta.attached_bus, self.local_meta.serving_object_path
            for interface, changed_properties in changes.items():
                if bus is not None and path is not None:
                    bus.emit_properties_changed(
                        path,
                        interface,
                        [prop.dbus_property.name for prop in changed_properties],
                    )
                self.emit_properties_changed_to_callbacks(changed_properties)


class ProxyPropertiesChangedSignal(
    BoundPropertiesChangedSignal, DbusProxySignal[DBUS_PROPERTIES_CHANGED_TYPING]
):
    pass


class DbusPropertiesInterface(
    DbusInterface,
    interface_name="org.freedesktop.DBus.Properties",
    serving_enabled=False,
):
    properties_changed = PropertiesChangedSignal(signature="sa{sv}as")

    @dbus_method("s", "a{sv}", name="GetAll")
    async def _properties_get_all(self, interface_name: str) -> Dict[str, Tuple[str, Any]]:
        raise NotImplementedError

    async def properties_get_all_dict(
        self,
        on_unknown_member: Literal["error", "ignore", "reuse"] = "error",
    ) -> Dict[str, Any]:

        properties: Dict[str, Any] = {}

        for interface_name, interface_cls in self.dbus_interfaces.items():
            meta = interface_cls.dbus_meta

            if meta is None:
                continue

            if not meta.serving_enabled:
                continue

            dbus_properties_data = await self._properties_get_all(interface_name)

            properties.update(
                _parse_properties_vardict(
                    meta.member_to_attr,
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
