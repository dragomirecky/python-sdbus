import os.path
from typing import Any, Tuple, cast

from textual import work
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from aiodbus.interface.daemon import FreedesktopDbus
from aiodbus.interface.properties import DbusPropertiesInterface
from aiodbus.tui.introspect import Method, Property, Signal, introspect


class Interfaces(Widget):
    def __init__(self, service_name: str):
        self._daemon = FreedesktopDbus()
        self._service_name = service_name
        self._objects: dict[str, TreeNode] = dict()
        self._interfaces: dict[Tuple[str, str], TreeNode] = dict()
        self._members: dict[Tuple[str, str, str], TreeNode] = dict()
        self._property_values: dict[Tuple[str, str, str], Any] = dict()
        super().__init__()

    async def on_mount(self) -> None:
        self._introspect_node("/")

    def compose(self) -> ComposeResult:
        tree = Tree("/")
        self._objects["/"] = tree.root
        tree.root.expand()
        yield tree

    def get_node_parent(self, path: str) -> TreeNode:
        parent, _ = os.path.split(path)
        if parent in self._objects:
            return self._objects[parent]
        else:
            return self.get_node_parent(parent)

    def get_or_create_object(self, path: str) -> TreeNode:
        if path not in self._objects:
            parent_node = self.get_node_parent(path)
            node = parent_node.add(path, expand=True)
            self._objects[path] = node
        return self._objects[path]

    def get_or_create_interface(self, path: str, interface_name: str) -> TreeNode:
        if (path, interface_name) not in self._interfaces:
            expand = not interface_name.startswith("org.freedesktop.DBus")
            node = self.get_or_create_object(path).add(interface_name, expand=expand)
            self._interfaces[(path, interface_name)] = node
        return self._interfaces[(path, interface_name)]

    def get_or_create_member(self, path: str, interface_name: str, member_name: str) -> TreeNode:
        if (path, interface_name, member_name) not in self._members:
            node = self.get_or_create_interface(path, interface_name).add_leaf(member_name)
            self._members[(path, interface_name, member_name)] = node
        return self._members[(path, interface_name, member_name)]

    def update_member_node(self, node: TreeNode, member: Method | Signal | Property):
        node.data = member
        if isinstance(member, Method):
            self.setup_method_node(node)
        elif isinstance(member, Signal):
            self.setup_signal_node(node)
        elif isinstance(member, Property):
            self.setup_property_node(node)

    def setup_method_node(self, node: TreeNode):
        method = cast(Method, node.data)
        input_str = ", ".join(
            f"{arg.name}: {arg.type}" for arg in method.args if arg.direction == "in"
        )
        output_str = ", ".join(
            f"{arg.name}: {arg.type}" for arg in method.args if arg.direction == "out"
        )
        signature_str = f"{method.name}({input_str}) -> ({output_str})"
        node.label = f"{signature_str}"

    def setup_property_node(self, node: TreeNode, value: Any = None):
        property = cast(Property, node.data)
        value_str = f"{value}" if value is not None else "..."
        node.label = f"{property.name}: {property.type} = {value_str}"

    def setup_signal_node(self, node: TreeNode):
        signal = cast(Signal, node.data)
        output_str = ", ".join(
            f"{arg.name}: {arg.type}" for arg in signal.args if arg.direction == "out"
        )
        signature_str = f"{signal.name} -> ({output_str})"
        node.label = f"{signature_str}"

    @work
    async def _introspect_node(self, path: str):
        node_intro = await introspect(self._service_name, path)
        if len(node_intro.interfaces) > 3:
            for interface in node_intro.interfaces:
                self.get_or_create_interface(path, interface.name)
                fetch_properties = False
                for member in interface.methods + interface.signals + interface.properties:
                    self.update_member_node(
                        self.get_or_create_member(path, interface.name, member.name), member
                    )
                    if isinstance(member, Property):
                        fetch_properties = True
                if fetch_properties:
                    self._fetch_properties(path, interface.name)
        for node_intro in node_intro.nodes:
            subpath = os.path.join(path, node_intro.name)
            self._introspect_node(subpath)

    @work
    async def _fetch_properties(self, path: str, interface_name: str):
        interface = DbusPropertiesInterface.new_proxy(self._service_name, object_path=path)
        properties = await interface._properties_get_all(interface_name)
        for name, value_tuple in properties.items():
            value_signature, value = value_tuple
            self._property_values[(path, interface_name, name)] = value
            node = self.get_or_create_member(path, interface_name, name)
            self.setup_property_node(node, value=value)
