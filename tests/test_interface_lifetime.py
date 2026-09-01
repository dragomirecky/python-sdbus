# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2025, Alan Dragomirecký

# This file is part of aiodbus, a fork of python-sdbus.

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
"""SdBusInterface is traversed by the garbage collector, which means the collector may
now reclaim one. These tests pin down when it must NOT: sd-bus keeps only a borrowed
pointer to the interface serving a path, so an interface freed while its vtable is still
registered would be a use-after-free on the next incoming call."""
from __future__ import annotations

import weakref
from gc import collect, get_objects
from unittest import main

from _sdbus import SdBusInterface
from aiodbus import DbusInterfaceCommon, dbus_method, dbus_property
from aiodbus.bus.sdbus import SdBus, SdBusServingInterface
from aiodbus.exceptions import MethodCallError
from aiodbus.meta import DbusLocalObjectMeta
from aiodbus.unittest import IsolatedDbusTestCase

TEST_SERVICE_NAME = "org.example.lifetime"


class CollectingInterface(
    DbusInterfaceCommon,
    interface_name="org.example.lifetime",
):
    def __init__(self) -> None:
        super().__init__()
        self.collections = 0

    @dbus_method("s", "s")
    async def echo_and_collect(self, value: str) -> str:
        """Collect from inside a call: the interface is serving this very request."""
        self.collections += collect()
        return value

    @dbus_property("s")
    def prop_and_collect(self) -> str:
        collect()
        return "property"


class TestInterfaceLifetime(IsolatedDbusTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await self.bus.request_name(TEST_SERVICE_NAME)

    def test_uninitialized_interface_survives_collection(self) -> None:
        """__new__ without __init__ leaves every member NULL; traversing that must be
        safe, because allocation itself can trigger a collection."""
        interface = SdBusInterface.__new__(SdBusInterface)
        collect()

        self.assertIsNone(interface.method_list)

    async def test_collection_during_a_method_call(self) -> None:
        served = CollectingInterface()
        export = served.export_to_dbus("/")
        proxy = CollectingInterface.new_proxy(TEST_SERVICE_NAME, "/")

        for _ in range(10):
            self.assertEqual("hello", await proxy.echo_and_collect("hello"))

        self.assertGreater(served.collections, 0)
        export.close()

    async def test_collection_during_a_property_read(self) -> None:
        served = CollectingInterface()
        export = served.export_to_dbus("/")
        proxy = CollectingInterface.new_proxy(TEST_SERVICE_NAME, "/")

        for _ in range(10):
            self.assertEqual("property", await proxy.prop_and_collect.get())

        export.close()

    async def test_exported_interface_outlives_dropped_local_object(self) -> None:
        """The exported object is held weakly by its members, so it goes away while the
        interface stays registered. Calls must still reach sd-bus, not freed memory."""
        served = CollectingInterface()
        served.export_to_dbus("/")
        proxy = CollectingInterface.new_proxy(TEST_SERVICE_NAME, "/")
        served_ref = weakref.ref(served)

        del served
        collect()
        self.assertIsNone(served_ref())

        await proxy.dbus_introspect()

    async def test_interface_freed_while_its_vtable_is_registered(self) -> None:
        """sd-bus keeps only a borrowed pointer to the interface as the vtable's
        userdata, so freeing the interface has to unregister the vtable -- even when
        something else still holds the slot that would otherwise have done it."""
        served = CollectingInterface()
        served.export_to_dbus("/")
        proxy = CollectingInterface.new_proxy(TEST_SERVICE_NAME, "/")
        self.assertEqual("first", await proxy.echo_and_collect("first"))

        meta = served._dbus
        assert isinstance(meta, DbusLocalObjectMeta)
        serving = meta.activated_interfaces[0]
        assert isinstance(serving, SdBusServingInterface)
        slot = serving._interface.slot

        # Drop everything holding the interface without unexporting it.
        bus = self.bus
        assert isinstance(bus, SdBus)
        bus._exported.clear()
        del served, meta, serving
        collect()

        with self.assertRaises(MethodCallError):
            await proxy.echo_and_collect("second")
        self.assertIsNotNone(slot)

    async def test_repeated_export_and_unexport(self) -> None:
        """Churn with a collection between each cycle: every round must serve calls
        correctly, and the interfaces must not accumulate."""

        def live_interfaces() -> int:
            return sum(1 for o in get_objects() if isinstance(o, SdBusInterface))

        for _ in range(3):  # warm up caches before taking the baseline
            served = CollectingInterface()
            export = served.export_to_dbus("/")
            export.close()
            del served, export
        collect()
        baseline = live_interfaces()

        for _ in range(20):
            served = CollectingInterface()
            export = served.export_to_dbus("/")
            proxy = CollectingInterface.new_proxy(TEST_SERVICE_NAME, "/")
            self.assertEqual("round", await proxy.echo_and_collect("round"))
            export.close()
            del served, export, proxy
            collect()

        self.assertEqual(baseline, live_interfaces())


if __name__ == "__main__":
    main()
