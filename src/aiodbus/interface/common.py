from aiodbus.interface.introspectable import DbusIntrospectable
from aiodbus.interface.peer import DbusPeerInterface
from aiodbus.interface.properties import DbusPropertiesInterface


class DbusInterfaceCommon(DbusPeerInterface, DbusPropertiesInterface, DbusIntrospectable): ...
