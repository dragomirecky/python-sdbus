import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List

from aiodbus.interface.introspectable import DbusIntrospectable


# Represents an argument for a method, signal, etc.
@dataclass
class Arg:
    type: str
    name: str = ""
    direction: str = ""


# Represents an annotation (used for properties)
@dataclass
class Annotation:
    name: str
    value: str


# Base class for interface members
@dataclass
class Member:
    name: str


# A method has a list of arguments
@dataclass
class Method(Member):
    args: List[Arg] = field(default_factory=list)


# A signal also has a list of arguments
@dataclass
class Signal(Member):
    args: List[Arg] = field(default_factory=list)


# A property has a type, access permissions, and may include annotations
@dataclass
class Property(Member):
    type: str = ""
    access: str = ""
    annotations: List[Annotation] = field(default_factory=list)


# An interface contains methods, signals, and properties
@dataclass
class Interface:
    name: str
    methods: List[Method] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    properties: List[Property] = field(default_factory=list)


# A node may have a name, a list of interfaces, and child nodes (subnodes)
@dataclass
class Node:
    name: str = ""
    interfaces: List[Interface] = field(default_factory=list)
    nodes: List["Node"] = field(default_factory=list)


def parse_introspection(xml_str: str) -> Node:
    """Parse the introspection XML string into a Node dataclass."""
    root = ET.fromstring(xml_str)
    return parse_node(root)


def parse_node(elem: ET.Element) -> Node:
    node_name = elem.get("name") or ""
    node_obj = Node(name=node_name)
    # Process each <interface> element as an Interface
    for iface_elem in elem.findall("interface"):
        node_obj.interfaces.append(parse_interface(iface_elem))
    # Process any nested <node> elements (subnodes)
    for subnode in elem.findall("node"):
        node_obj.nodes.append(parse_node(subnode))
    return node_obj


def parse_interface(elem: ET.Element) -> Interface:
    iface_name = elem.get("name") or ""
    interface = Interface(name=iface_name)
    # Process children which could be methods, signals, or properties.
    for child in elem:
        if child.tag == "method":
            interface.methods.append(parse_method(child))
        elif child.tag == "signal":
            interface.signals.append(parse_signal(child))
        elif child.tag == "property":
            interface.properties.append(parse_property(child))
    return interface


def parse_method(elem: ET.Element) -> Method:
    method_name = elem.get("name") or ""
    method = Method(name=method_name)
    for arg_elem in elem.findall("arg"):
        method.args.append(parse_arg(arg_elem, default_dir="in"))
    return method


def parse_signal(elem: ET.Element) -> Signal:
    signal_name = elem.get("name") or ""
    signal = Signal(name=signal_name)
    for arg_elem in elem.findall("arg"):
        signal.args.append(parse_arg(arg_elem, default_dir="out"))
    return signal


def parse_property(elem: ET.Element) -> Property:
    prop_name = elem.get("name") or ""
    prop_type = elem.get("type") or ""
    access = elem.get("access") or ""
    property_obj = Property(name=prop_name, type=prop_type, access=access)
    # Parse any annotations for the property.
    for ann in elem.findall("annotation"):
        property_obj.annotations.append(parse_annotation(ann))
    return property_obj


def parse_arg(elem: ET.Element, default_dir: str = "") -> Arg:
    arg_type = elem.get("type") or ""
    arg_name = elem.get("name") or ""
    direction = elem.get("direction") or default_dir
    return Arg(type=arg_type, name=arg_name, direction=direction)


def parse_annotation(elem: ET.Element) -> Annotation:
    ann_name = elem.get("name") or ""
    ann_value = elem.get("value") or ""
    return Annotation(name=ann_name, value=ann_value)


async def introspect(service_name: str, path: str = "/") -> Node:
    service = DbusIntrospectable.new_proxy(service_name, object_path=path)
    introspection = await service.dbus_introspect()
    return parse_introspection(introspection)
