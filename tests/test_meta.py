from aiodbus.interface.base import DbusInterface, DbusInterfaceMeta
from aiodbus.member.method import dbus_method


def test_basic_toplevel_interface():

    class MyInterface(DbusInterface, interface_name="com.example.MyInterface_10"):
        pass

    assert MyInterface.dbus_interfaces == {"com.example.MyInterface_10": MyInterface}


def test_multiple_interfaces():
    class MyInterface(DbusInterface, interface_name="com.example.MyInterface_20"):
        pass

    class MyInterface2(DbusInterface, interface_name="com.example.MyInterface_21"):
        pass

    class MyInterface3(MyInterface, MyInterface2, interface_name="com.example.MyInterface_22"):
        pass

    assert MyInterface3.dbus_interfaces == {
        "com.example.MyInterface_20": MyInterface,
        "com.example.MyInterface_21": MyInterface2,
        "com.example.MyInterface_22": MyInterface3,
    }


def test_default_unprivileged_applies_to_methods():
    class MyInterface(
        DbusInterface,
        interface_name="com.example.MyInterface_30",
        default_unprivileged=True,
    ):
        @dbus_method()
        async def my_method(self) -> None: ...

    assert vars(MyInterface)["my_method"].flags["unprivileged"] is True


def test_default_unprivileged_does_not_override_explicit():
    class MyInterface(
        DbusInterface,
        interface_name="com.example.MyInterface_31",
        default_unprivileged=True,
    ):
        @dbus_method(unprivileged=False)
        async def my_method(self) -> None: ...

    assert vars(MyInterface)["my_method"].flags["unprivileged"] is False


def test_default_unprivileged_absent_leaves_flags_empty():
    class MyInterface(
        DbusInterface,
        interface_name="com.example.MyInterface_32",
    ):
        @dbus_method()
        async def my_method(self) -> None: ...

    assert "unprivileged" not in vars(MyInterface)["my_method"].flags
