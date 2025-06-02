from __future__ import annotations

import logging
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import (
    Any,
    ContextManager,
    Dict,
    Iterable,
    List,
    Optional,
    Self,
    Tuple,
    Type,
    Union,
    overload,
    override,
)

from aiodbus.interface.base import DbusInterface
from aiodbus.member.base import DbusClassMember
from aiodbus.member.method import dbus_method
from aiodbus.member.property import DbusBoundProperty, DbusLocalProperty, DbusProperty
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
    def __get__[I: DbusInterface](
        self, obj: None, obj_class: Type[I]
    ) -> DbusClassMember[I, DbusSignal[DBUS_PROPERTIES_CHANGED_TYPING]]: ...

    @overload
    def __get__[I: DbusInterface](
        self, obj: I, obj_class: Type[I]
    ) -> BoundPropertiesChangedSignal[I]: ...

    def __get__[I: DbusInterface](  # type: ignore[override]
        self, obj: Optional[I], obj_class: Optional[Type[I]] = None
    ) -> Union[
        BoundPropertiesChangedSignal[I],
        DbusClassMember[I, DbusSignal[DBUS_PROPERTIES_CHANGED_TYPING]],
    ]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return ProxyPropertiesChangedSignal(
                    member=self, local_object=obj, proxy_meta=dbus_meta
                )
            else:
                return LocalPropertiesChangedSignal(
                    member=self, local_object=obj, local_meta=dbus_meta
                )
        else:
            assert obj_class is not None
            return DbusClassMember[I, DbusSignal[DBUS_PROPERTIES_CHANGED_TYPING]](
                local_object_cls=obj_class, member=self
            )


class BoundPropertiesChangedSignal[I: DbusInterface](
    DbusBoundSignal[I, DBUS_PROPERTIES_CHANGED_TYPING]
):
    def emit_property_changed(self, prop: DbusBoundProperty):
        raise NotImplementedError

    def grouped_changes(self) -> ContextManager[None]:
        raise NotImplementedError


class LocalPropertiesChangedSignal[I: DbusInterface](
    BoundPropertiesChangedSignal[I], DbusLocalSignal[I, DBUS_PROPERTIES_CHANGED_TYPING]
):
    def emit_properties_changed_to_callbacks(self, changes: set[DbusBoundProperty]):
        if not self.member.local_callbacks:
            return

        for prop in changes:
            assert isinstance(prop, DbusLocalProperty)
            value = prop._get_value()
            signal_value: DBUS_PROPERTIES_CHANGED_TYPING = (
                prop.member.interface_name,
                {
                    prop.member.name: (
                        prop.member.signature,
                        value,
                    ),
                },
                [],
            )

            for callback in self.member.local_callbacks:
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
            changes[prop.member.interface_name].add(prop)
        except LookupError:
            dbus.emit_properties_changed(
                path=path,
                interface=prop.member.interface_name,
                properties=[prop.member.name],
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
            bus, path = (
                self.local_meta.attached_bus,
                self.local_meta.serving_object_path,
            )
            for interface, changed_properties in changes.items():
                if bus is not None and path is not None:
                    bus.emit_properties_changed(
                        path,
                        interface,
                        [prop.member.name for prop in changed_properties],
                    )
                self.emit_properties_changed_to_callbacks(changed_properties)


class ProxyPropertiesChangedSignal[I: DbusInterface](
    BoundPropertiesChangedSignal[I], DbusProxySignal[I, DBUS_PROPERTIES_CHANGED_TYPING]
):
    pass


@dataclass(frozen=True)
class PropertiesChangedData[I: DbusInterface]:
    interface: str
    changed: PropertiesDict[I]
    invalidated: List[str]


def parse_properties_changed(
    data: DBUS_PROPERTIES_CHANGED_TYPING,
) -> PropertiesChangedData:
    interface_name, changed_raw, invalidated = data

    changed = PropertiesDict()
    for member_name, variant in changed_raw.items():
        changed[(interface_name, member_name)] = variant[1]

    return PropertiesChangedData(
        interface=interface_name,
        changed=changed,
        invalidated=invalidated,
    )


class PropertiesDict[I: DbusInterface](dict[tuple[str, str], Any]):
    """
    Dictionary of properties of some D-Bus Object.
    Keys are (interface_name, property_name) tuples.
    """

    @overload
    def __getitem__(self, key: tuple[str, str]) -> Any: ...

    @overload
    def __getitem__[T](self, key: DbusBoundProperty[I, T]) -> T: ...

    @overload
    def __getitem__[T](self, key: DbusClassMember[I, DbusProperty[T]]) -> T: ...

    def __getitem__[T](
        self,
        key: Union[tuple[str, str], DbusBoundProperty[I, T], DbusClassMember[I, DbusProperty[T]]],
    ):
        if isinstance(key, DbusBoundProperty):
            property = key.member
            return self[(property.interface_name, property.name)]
        elif isinstance(key, DbusClassMember):
            property = key.member
            return self[(property.interface_name, property.name)]
        else:
            return super().__getitem__(key)

    def update_with_properties_changed(self, data: PropertiesChangedData[I]) -> None:
        self.update(data.changed)
        for invalidated_property in data.invalidated:
            try:
                del self[(data.interface, invalidated_property)]
            except KeyError:
                pass

    @override
    def copy(self) -> PropertiesDict[I]:
        return PropertiesDict(self)


class DbusPropertiesInterface(
    DbusInterface,
    interface_name="org.freedesktop.DBus.Properties",
    serving_enabled=False,
):
    properties_changed = PropertiesChangedSignal(signature="sa{sv}as")

    @dbus_method("s", "a{sv}", name="GetAll")
    async def _properties_get_all(self, interface_name: str) -> Dict[str, Tuple[str, Any]]:
        raise NotImplementedError

    async def properties_get_all(
        self,
        interfaces: Optional[Iterable[str]] = None,
    ) -> PropertiesDict[Self]:
        properties = PropertiesDict[Self]()
        interfaces = [
            interface
            for interface, interface_cls in self.dbus_interfaces.items()
            if interface_cls.dbus_meta is not None and interface_cls.dbus_meta.serving_enabled
        ]

        for interface_name in interfaces:
            dbus_properties_data = await self._properties_get_all(interface_name)

            for dbus_name, variant in dbus_properties_data.items():
                properties[(interface_name, dbus_name)] = variant[1]

        return properties
