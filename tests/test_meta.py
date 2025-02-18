from aiodbus.interface.base import DbusInterface, DbusInterfaceMeta


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
