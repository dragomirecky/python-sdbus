Blocking quick start
+++++++++++++++++++++

.. py:currentmodule:: sdbus

Interface classes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Python-sdbus works by declaring interface classes.

Interface classes for blocking IO should be derived from :py:class:`DbusInterfaceCommon`.

The class constructor takes ``interface_name`` keyword to determine the D-Bus interface name for all
D-Bus elements declared in the class body.

Example::

    class ExampleInterface(DbusInterfaceCommon,
                           interface_name='org.example.myinterface'
                           ):
        ...

Interface class body should contain the definitions of methods and properties using the decorators
:py:func:`dbus_method` and :py:func:`dbus_property` respectively.

Example::

    from sdbus import (DbusInterfaceCommon,
                       dbus_method, dbus_property)


    class ExampleInterface(DbusInterfaceCommon,
                           interface_name='org.example.myinterface'
                           ):
        # Method that takes an integer and does not return anything
        @dbus_method('u')
        def close_notification(self, an_int: int) -> None:
            raise NotImplementedError

        # Read only property of int
        @dbus_property()
        def test_int(self) -> int:
            raise NotImplementedError

This is an interface of that defines a one D-Bus method and one property.

The actual body of the decorated function will not be called. Instead the call will be routed
through D-Bus to a another process. Interface can have non-decorated functions that will act
as regular methods.

Blocking IO can only interact with existing D-Bus objects and can not be
served for other processes to interact with. See :ref:`blocking-vs-async`

Initiating proxy
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:py:meth:`DbusInterfaceCommon.__init__` method takes service_name
and object_path of the remote object that the object will proxy to.

Example creating a proxy and calling method::

    ...
    # Initialize the object
    d = ExampleInterface(
        service_name='org.example.test',
        object_path='/',
    )

    d.close_notification(1234)

.. note:: Successfully initiating a proxy object does NOT guarantee that the D-Bus object
          exists.

Methods
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Methods are functions wrapped with :py:func:`dbus_method` decorator.

If the remote object sends an error reply an exception with base of :py:exc:`.DbusFailedError`
will be raised. See :doc:`/exceptions` for list of exceptions.

The wrapped function will not be called. Its recommended to set the function to ``raise NotImplementedError``.

Example: ::

    from sdbus import DbusInterfaceCommon, dbus_method


    class ExampleInterface(...):

        ...
        # Body of some class

        @dbus_method('u')
        def close_notification(self, an_int: int) -> None:
            raise NotImplementedError

Properties
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

D-Bus property is defined by wrapping a function with :py:func:`dbus_property` decorator.

Example: ::

    from sdbus import DbusInterfaceCommon, dbus_property

    class ExampleInterface(...):

        ...
        # Body of some class

        # Property of str
        @dbus_property('s')
        def test_string(self) -> str:
            raise NotImplementedError

The new property behaves very similar to Pythons :py:func:`property` decorator. ::

    # Initialize the proxy
    d = ExampleInterface(
        service_name='org.example.test',
        object_path='/',
    )

    # Print it
    print(d.test_string)

    # Assign new string
    d.test_string = 'some_string'

If property is read-only when :py:exc:`.DbusPropertyReadOnlyError` will be raised.

Multiple interfaces
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A D-Bus object can have multiple interfaces with different methods and properties.

To implement this define multiple interface classes and do a
multiple inheritance on all interfaces the object has.

Example: ::

    from sdbus import DbusInterfaceCommon, dbus_method


    class ExampleInterface(DbusInterfaceCommon,
                           interface_name='org.example.myinterface'
                           ):

        @dbus_method('i')
        def example_method(self, an_int: int) -> None:
            raise NotImplementedError


    class TestInterface(DbusInterfaceCommon,
                        interface_name='org.example.test'
                        ):

        @dbus_method('as')
        def test_method(self, str_array: List[str]) -> None:
            raise NotImplementedError


    class MultipleInterfaces(TestInterface, ExampleInterface):
        ...

``MultipleInterfaces`` class will have both ``test_method`` and ``example_method``
that will be proxied to correct interface names. (``org.example.myinterface``
and ``org.example.test`` respectively)
