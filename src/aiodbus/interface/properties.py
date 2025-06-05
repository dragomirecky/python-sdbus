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
    assert_never,
    cast,
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
from aiodbus.meta import DbusClassMeta, DbusRemoteObjectMeta

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
class PropertiesChangedData[I: DbusPropertiesInterface]:
    interface: Type[DbusPropertiesInterface]
    changed: PropertiesDict[I]
    invalidated: List[DbusProperty]


def parse_properties_changed[T: DbusPropertiesInterface](
    data: DBUS_PROPERTIES_CHANGED_TYPING, interface: Type[T]
) -> PropertiesChangedData:
    interface_name, changed_raw, invalidated = data

    changed = PropertiesDict[T]()
    property_interface = interface.dbus_interfaces[interface_name]
    interface_meta = cast(DbusClassMeta, property_interface.dbus_meta)

    for member_name, variant in changed_raw.items():
        attr = interface_meta.member_to_attr[member_name]
        member = cast(DbusClassMember, getattr(property_interface, attr)).member
        value = member.mapping.conversion.to_dbus(variant[1])
        changed[member] = value

    invalidated_props = []
    for invalidated_property_name in invalidated:
        attr = interface_meta.member_to_attr[invalidated_property_name]
        member = cast(DbusClassMember, getattr(property_interface, attr)).member
        value = member.mapping.conversion.to_dbus(None)
        invalidated_props.append(value)

    return PropertiesChangedData(
        interface=cast(Type[DbusPropertiesInterface], property_interface),
        changed=changed,
        invalidated=invalidated_props,
    )


class PropertiesDict[I: DbusPropertiesInterface](dict[DbusProperty, Any]):
    """
    Dictionary of properties of some D-Bus Object.
    Keys are (interface_name, property_name) tuples.
    """

    @overload
    def __getitem__[T](self, key: DbusBoundProperty[I, T]) -> T: ...

    @overload
    def __getitem__[T](self, key: DbusClassMember[I, DbusProperty[T]]) -> T: ...

    @overload
    def __getitem__[T](self, key: DbusProperty[T]) -> T: ...

    def __getitem__[T](
        self,
        key: DbusProperty[T]
        | DbusBoundProperty[I, T]
        | DbusClassMember[I, DbusProperty[T]],
    ):
        match key:
            case DbusBoundProperty() | DbusClassMember():
                return super().__getitem__(key.member)
            case DbusProperty():
                return super().__getitem__(key)
            case _:
                assert_never(key)

    def update_with_properties_changed(self, data: PropertiesChangedData[I]) -> None:
        self.update(data.changed)
        for invalidated_property in data.invalidated:
            try:
                del self[invalidated_property]
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
    async def _properties_get_all(
        self, interface_name: str
    ) -> Dict[str, Tuple[str, Any]]:
        properties: Dict[str, Tuple[str, Any]] = {}
        try:
            interface = self.dbus_interfaces[interface_name]
        except KeyError:
            raise ValueError(
                f"Interface {interface_name!r} not found in {self.__class__.__name__}"
            )

        interface_meta = cast(DbusClassMeta, interface.dbus_meta)
        for member_attr, member in interface_meta.members.items():
            if isinstance(member, DbusProperty):
                bound_member = cast(DbusBoundProperty, getattr(self, member_attr))
                value = await bound_member.get()
                dbus_value = member.mapping.conversion.to_dbus(value)
                properties[member.name] = (member.signature, dbus_value)
        return properties

    async def properties_get_all(
        self,
        interfaces: Optional[Iterable[Type[DbusPropertiesInterface]]] = None,
    ) -> PropertiesDict[Self]:
        properties = PropertiesDict[Self]()

        if interfaces is None:
            interfaces = [
                cast(Type[DbusPropertiesInterface], interface_cls)
                for interface_cls in self.dbus_interfaces.values()
                if interface_cls.dbus_meta is not None
                and interface_cls.dbus_meta.serving_enabled
            ]

        for interface in interfaces:
            dbus_meta = cast(DbusClassMeta, interface.dbus_meta)
            dbus_properties_data = await self._properties_get_all(
                dbus_meta.interface_name
            )
            for member_name, variant in dbus_properties_data.items():
                attr_name = dbus_meta.member_to_attr[member_name]
                member = cast(DbusClassMember, getattr(interface, attr_name)).member
                properties[member] = member.mapping.conversion.from_dbus(variant[1])

        return properties
