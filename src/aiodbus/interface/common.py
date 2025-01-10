from aiodbus.interface.introspectable import DbusIntrospectableAsync
from aiodbus.interface.peer import DbusPeerInterfaceAsync
from aiodbus.interface.properties import DbusPropertiesInterfaceAsync


class DbusInterfaceCommonAsync(
    DbusPeerInterfaceAsync, DbusPropertiesInterfaceAsync, DbusIntrospectableAsync
): ...
