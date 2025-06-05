import inspect
from enum import IntEnum, auto
from functools import lru_cache
from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    Protocol,
    Self,
    Sequence,
    assert_never,
    get_args,
    get_origin,
)

from aiodbus.basic_types import (
    DbusCompleteType,
    DbusCompleteTypes,
)


class DbusConvertible[T, D: DbusCompleteType](Protocol):
    """
    Provides information on how to bridge some Python type to its D-Bus representation.

    It is recommended not to inherit from this class directly. Just make sure that the object
    you pass to WithConversion annotation has the following fields.
    (this way, if you make the `signature` a ClassVar and to_dbus/from_dbus static methods,
    you can use the class itself as the DbusConvertible object).
    """

    signature: str
    """
    D-Bus signature of the type (single complete type).
    """

    def to_dbus(self, value: T) -> D:
        """
        Converts a Python value to its D-Bus representation.
        """
        ...

    def from_dbus(self, value: D) -> T:
        """
        Converts a D-Bus representation to a Python value.
        """
        ...


class DbusNativeType:
    """
    Bridge for D-bus native types (like `int`, `str`, etc.).
    """

    @lru_cache(maxsize=64)
    def __new__(cls, signature: str):  # type: ignore
        return super().__new__(cls)

    __slots__ = ("signature",)

    def __init__(self, signature: str) -> None:
        self.signature = signature

    def to_dbus(self, value: Any) -> DbusCompleteType:
        return value

    def from_dbus(self, value: DbusCompleteType) -> Any:
        return value

    def __str__(self) -> str:
        return f"DbusNativeType({self.signature})"


class WithName:
    """
    Mark an input or output parameter to have a specific name in D-Bus method signature.

    Usage:
        ```python
        @dbus_method
        async def my_method() -> Annotated[int, WithName("my_result")]:
            ...
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


class WithConversion:
    """
    Type annotation for specifying what `DbusConvertible` to use for a parameter or return type.

    Usage:

        ```python

        class MyDbusConversion:
            ... (implement DbusConvertible methods/fields)

        @dbus_method
        async def my_method(my_arg: Annotated[int, WithConversion(MyDbusConversion())]):
            ...

        ```
    """

    __slots__ = ("representable",)

    def __init__(self, representable: DbusConvertible) -> None:
        self.representable = representable


DbusByte = Annotated[int, WithConversion(DbusNativeType("y"))]
DbusBool = Annotated[bool, WithConversion(DbusNativeType("b"))]
DbusInt16 = Annotated[int, WithConversion(DbusNativeType("n"))]
DbusUint16 = Annotated[int, WithConversion(DbusNativeType("q"))]
DbusInt32 = Annotated[int, WithConversion(DbusNativeType("i"))]
DbusUint32 = Annotated[int, WithConversion(DbusNativeType("u"))]
DbusInt64 = Annotated[int, WithConversion(DbusNativeType("x"))]
DbusUint64 = Annotated[int, WithConversion(DbusNativeType("t"))]
DbusDouble = Annotated[float, WithConversion(DbusNativeType("d"))]
DbusUnixFd = Annotated[int, WithConversion(DbusNativeType("h"))]
DbusObjectAsString = Annotated[str, WithConversion(DbusNativeType("o"))]


class _DbusList:
    """
    Implements conversion of "list[T]" type to D-Bus representation.
    """

    def __new__(cls, type: type) -> DbusConvertible:
        # optimization:
        # if the given element type is a native dbus type, return a native type for list
        # effectively becomes no-op for lists of native types
        element_type = get_args(type)[0]
        element_conversion = get_dbus_conversion(element_type)
        if isinstance(element_conversion, DbusNativeType):
            return DbusNativeType(f"a{element_conversion.signature}")
        else:
            return super().__new__(cls)

    __slots__ = ("element_type", "element_conversion", "signature")

    def __init__(self, type: type) -> None:
        self.element_type = get_args(type)[0]
        self.element_conversion = get_dbus_conversion(self.element_type)
        self.signature = f"a{self.element_conversion.signature}"

    def to_dbus(self, value: Any) -> DbusCompleteType:
        if not isinstance(value, list):
            raise TypeError(f"Expected a list, got {type(value).__name__}")
        return [self.element_conversion.to_dbus(item) for item in value]

    def from_dbus(self, value: DbusCompleteType) -> Any:
        if not isinstance(value, list):
            raise TypeError(f"Expected a list, got {type(value).__name__}")
        return [self.element_conversion.from_dbus(item) for item in value]

    def __str__(self) -> str:
        return f"DbusList(signature={self.signature})"


class _DbusDict:
    """
    Implements conversion of "dict[K, V]" type to D-Bus representation.
    """

    def __new__(cls, type: type) -> DbusConvertible:
        # optimization:
        # if the given type is a dict with native key and value types, return a native type for dict
        # effectively becomes no-op for dicts of native types
        key_type, value_type = get_args(type)
        key_conversion = get_dbus_conversion(key_type)
        value_conversion = get_dbus_conversion(value_type)
        if isinstance(key_conversion, DbusNativeType) and isinstance(
            value_conversion, DbusNativeType
        ):
            return DbusNativeType(f"a{{{key_conversion.signature}{value_conversion.signature}}}")
        else:
            return super().__new__(cls)

    __slots__ = ("key_conversion", "value_conversion", "signature")

    def __init__(self, type: type) -> None:
        key_type, value_type = get_args(type)
        self.key_conversion = get_dbus_conversion(key_type)
        self.value_conversion = get_dbus_conversion(value_type)
        self.signature = f"a{{{self.key_conversion.signature}{self.value_conversion.signature}}}"

    def to_dbus(self, value: Any) -> DbusCompleteType:
        if not isinstance(value, dict):
            raise TypeError(f"Expected a dict, got {type(value).__name__}")
        return {
            self.key_conversion.to_dbus(key): self.value_conversion.to_dbus(val)
            for key, val in value.items()
        }

    def from_dbus(self, value: DbusCompleteType) -> Any:
        if not isinstance(value, dict):
            raise TypeError(f"Expected a dict, got {type(value).__name__}")
        return {
            self.key_conversion.from_dbus(key): self.value_conversion.from_dbus(val)
            for key, val in value.items()
        }

    def __str__(self) -> str:
        return f"DbusDict(signature={self.signature})"


class _DbusStruct:
    """
    Implements conversion of "tuple[T1, T2, ...]" type to D-Bus representation.
    """

    def __new__(cls, type: type) -> DbusConvertible:
        # optimization:
        # if the given type is a tuple of native dbus types, return a native type for it
        # effectively becomes no-op for tuples of native types
        element_types = get_args(type)
        element_conversions = [get_dbus_conversion(t) for t in element_types]
        if all(isinstance(conversion, DbusNativeType) for conversion in element_conversions):
            signature_inner = "".join(conversion.signature for conversion in element_conversions)
            return DbusNativeType(f"({signature_inner})")
        else:
            return super().__new__(cls)

    __slots__ = ("element_types", "element_conversions", "signature")

    def __init__(self, type: type) -> None:
        self.element_types = get_args(type)
        self.element_conversions = [get_dbus_conversion(t) for t in self.element_types]
        signature_inner = "".join(conversion.signature for conversion in self.element_conversions)
        self.signature = f"({signature_inner})"

    def to_dbus(self, value: tuple[Any, ...]) -> DbusCompleteType:
        if len(value) != len(self.element_types):
            raise ValueError(
                f"Expected tuple of length {len(self.element_types)}, got {len(value)}"
            )
        return tuple(
            self.element_conversions[i].to_dbus(value[i]) for i in range(len(self.element_types))
        )

    def from_dbus(self, value: DbusCompleteType) -> tuple[Any, ...]:
        if not isinstance(value, tuple):
            raise TypeError(f"Expected a tuple, got {type(value).__name__}")
        if len(value) != len(self.element_types):
            raise ValueError(
                f"Expected tuple of length {len(self.element_types)}, got {len(value)}"
            )
        return tuple(
            self.element_conversions[i].from_dbus(value[i]) for i in range(len(self.element_types))
        )

    def __str__(self) -> str:
        return f"DbusStruct(signature={self.signature})"


_default_conversions: dict[type, Callable[[type], DbusConvertible]] = {
    int: lambda _: DbusNativeType("i"),
    str: lambda _: DbusNativeType("s"),
    float: lambda _: DbusNativeType("d"),
    bool: lambda _: DbusNativeType("b"),
    list: _DbusList,
    dict: _DbusDict,
    tuple: _DbusStruct,
}


def register_conversion_factory(type: type, factory: Callable[[type], DbusConvertible]) -> None:
    _default_conversions[type] = factory


def _get_annotation[T](annotation_type: type[T], annotation) -> T | None:
    """
    Return the first annotation of the given type from the type's metadata.
    """
    if get_origin(annotation) is Annotated:
        for annotation in annotation.__metadata__:
            if isinstance(annotation, annotation_type):
                return annotation
    return None


def _get_bare_type(annotation) -> type:
    """
    Get the bare type from an annotation, removing any `Annotated` wrapper or associated types.

    E.g:
        get_bare_type(int) -> int
        get_bare_type(dict[str, int]) -> dict
        get_bare_type(Annotated[int, WithName("x")]) -> int
    """
    if get_origin(annotation) is Annotated:
        return _get_bare_type(annotation.__origin__)
    else:
        return get_origin(annotation) or annotation


@lru_cache()
def get_dbus_conversion(annotation: type) -> DbusConvertible:
    """
    Get the D-Bus conversion for a given type annotation.
    """
    representation: DbusConvertible | None = None
    if conversion := _get_annotation(WithConversion, annotation):
        representation = conversion.representable
    if not representation:
        if get_origin(annotation) is Annotated:
            unwrapped_annotated = annotation.__origin__
        else:
            unwrapped_annotated = annotation
        bare_type = get_origin(unwrapped_annotated) or unwrapped_annotated
        representation_factory = _default_conversions.get(bare_type, None)
        if representation_factory is None:
            raise ValueError(f"No dbus conversion found for type {bare_type}")
        representation = representation_factory(unwrapped_annotated)
    return representation


class _DbusNone:
    """
    Special D-Bus type representing `None` as a return value.
    """

    signature: ClassVar = ""

    @staticmethod
    def to_dbus(value: None) -> DbusCompleteTypes:
        return ()

    @staticmethod
    def from_dbus(value: DbusCompleteTypes) -> None:
        return None

    def __str__(self) -> str:
        return "DbusNone()"


class Parameter:
    """
    Prepared information about some Python method parameter.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    def from_parameter_inspection(cls, parameter: inspect.Parameter) -> Self:
        if parameter.annotation is inspect.Parameter.empty:
            raise ValueError(f"Parameter {parameter.name} has no type annotation.")
        if name_annotation := _get_annotation(WithName, parameter.annotation):
            name = name_annotation.name
        else:
            name = parameter.name
        return cls(name=name)


class _MultipleTypesConversion:
    __slots__ = ("input_conversions", "signature")

    def __init__(self, type: type) -> None:
        if get_origin(type) is not tuple:
            raise TypeError(f"Expected a tuple type, got {type}")
        input_annotations = [annotation for annotation in get_args(type)]
        self.input_conversions = [
            get_dbus_conversion(annotation) for annotation in input_annotations
        ]
        self.signature = "".join(conversion.signature for conversion in self.input_conversions)

    def to_dbus(self, value: tuple[Any, ...]) -> DbusCompleteTypes:
        if len(value) != len(self.input_conversions):
            raise ValueError(f"Expected {len(self.input_conversions)} arguments, got {len(value)}")
        return tuple(
            conversion.to_dbus(arg) for conversion, arg in zip(self.input_conversions, value)
        )

    def from_dbus(self, value: DbusCompleteTypes) -> tuple[Any, ...]:
        if len(value) != len(self.input_conversions):
            raise ValueError(f"Expected {len(self.input_conversions)} values, got {len(value)}")
        return tuple(
            conversion.from_dbus(val) for conversion, val in zip(self.input_conversions, value)
        )


class _ResultConversion:
    """
    Conversion of the return value of a Dbus method.

    Handles the following cases:
    - No return value (None) being sent to lower D-bus layer as an empty tuple `()`.
    - Single return value being sent as a single-element tuple `(value,)`.
    - Multiple return values being sent as a tuple of values, e.g. `(value1, value2, ...)`.
    """

    __slots__ = ("value_type", "conversion", "params", "signature")

    class ReturnValueType(IntEnum):
        NONE = auto()
        SINGLE = auto()
        TUPLE = auto()

    def __init__(self, return_annotation: type | None) -> None:
        if return_annotation is None:
            value_type = self.ReturnValueType.NONE
            conversion = _DbusNone
            params = []
        elif get_origin(return_annotation) is tuple:
            value_type = self.ReturnValueType.TUPLE
            tuple_args = return_annotation.__args__
            conversion = _MultipleTypesConversion(return_annotation)
            params = []
            for idx, arg in enumerate(tuple_args):
                if name_annotation := _get_annotation(WithName, arg):
                    name = name_annotation.name
                else:
                    name = f"out_{idx + 1}"
                params.append(Parameter(name=name))
        else:
            value_type = self.ReturnValueType.SINGLE
            conversion = get_dbus_conversion(return_annotation)
            if name_annotation := _get_annotation(WithName, return_annotation):
                name = name_annotation.name
            else:
                name = "out"
            params = [Parameter(name=name)]
        self.value_type = value_type
        self.conversion: DbusConvertible = conversion
        self.params = params
        self.signature = conversion.signature

    def to_dbus(self, value: Any) -> DbusCompleteTypes:
        match self.value_type:
            case self.ReturnValueType.NONE:
                return ()
            case self.ReturnValueType.SINGLE:
                return (self.conversion.to_dbus(value),)
            case self.ReturnValueType.TUPLE:
                return self.conversion.to_dbus(value)
            case _:
                assert_never(self.result_type)

    def from_dbus(self, value: DbusCompleteTypes) -> Any:
        match self.value_type:
            case self.ReturnValueType.NONE:
                return None
            case self.ReturnValueType.SINGLE:
                return self.conversion.from_dbus(value[0])
            case self.ReturnValueType.TUPLE:
                return self.conversion.from_dbus(value)
            case _:
                assert_never(self.result_type)


class ResultNativeTypeConversion:
    def __init__(self, signature: str):
        self.signature = signature

    def to_dbus(self, value: Any) -> DbusCompleteTypes:
        return value

    def from_dbus(self, value: DbusCompleteTypes) -> Any:
        assert isinstance(value, tuple)
        if len(value) == 0:
            return None
        elif len(value) == 1:
            return value[0]
        else:
            return value


class MethodMapping:

    __slots__ = ("input_params", "input_conversion", "result_params", "result_conversion")

    def __init__(
        self,
        input_params: list[Parameter],
        input_conversion: DbusConvertible,
        result_params: list[Parameter],
        result_conversion: DbusConvertible,
    ) -> None:
        self.input_params = input_params
        self.input_conversion = input_conversion
        self.result_params = result_params
        self.result_conversion = result_conversion

    @classmethod
    def from_callable(cls, callable: Callable) -> Self:
        signature = inspect.signature(callable, eval_str=True, follow_wrapped=True)
        bound_params = [
            p
            for i, (n, p) in enumerate(signature.parameters.items())
            if not (n == "self" and i == 0)
        ]

        input_params = [Parameter.from_parameter_inspection(p) for p in bound_params]
        input_annotations = [p.annotation for p in bound_params]
        input_conversion = _MultipleTypesConversion(tuple[*input_annotations])
        result_annotation = (
            signature.return_annotation
            if signature.return_annotation is not inspect.Signature.empty
            else None
        )
        result_conversion = _ResultConversion(result_annotation)

        return cls(
            input_params=input_params,
            input_conversion=input_conversion,
            result_params=result_conversion.params,
            result_conversion=result_conversion,
        )

    @classmethod
    def from_manual_input(
        cls,
        input_signature: str,
        result_signature: str,
        input_names: Sequence[str] | None,
        result_names: Sequence[str] | None,
        callable: Callable,
    ) -> Self:
        input_conversion = DbusNativeType(input_signature)
        result_conversion = ResultNativeTypeConversion(result_signature)

        # if the user entered result names but not input names,
        # we try to infer them
        # because with the names, it is all or nothing (either we
        # specify both input and result names, or none)
        # otherwise sd_bus fails
        if result_names is not None and input_names is None:
            signature = inspect.signature(callable, eval_str=True, follow_wrapped=True)
            input_names = [
                p.name
                for i, p in enumerate(signature.parameters.values())
                if not (p.name == "self" and i == 0)
            ]
        result_names = result_names or ()
        input_names = input_names or ()

        input_params = [Parameter(name=name) for name in input_names]
        result_params = [Parameter(name=name) for name in result_names]

        return cls(
            input_params=input_params,
            input_conversion=input_conversion,
            result_params=result_params,
            result_conversion=result_conversion,
        )


class NoGenericsTypingAvailable(Exception):
    pass


class PropertyMapping:
    """
    Represents a mapping of a D-Bus property to its Python representation.
    """

    __slots__ = ("conversion",)

    def __init__(self, conversion: DbusConvertible):
        self.conversion: DbusConvertible = conversion

    @classmethod
    def from_getter(cls, getter: Callable) -> Self:
        signature = inspect.signature(getter, eval_str=True, follow_wrapped=True)
        retval_annotation = signature.return_annotation
        if retval_annotation is inspect.Signature.empty:
            raise ValueError(f"Getter {getter.__name__} has no return type annotation.")
        conversion = get_dbus_conversion(retval_annotation)
        return cls(conversion=conversion)

    @classmethod
    def from_generics(cls, object, argument_idx: int) -> Self:
        """
        Create a PropertyMapping from a generic type annotation.
        The `argument_index` is the index of the type in the generic type.
        """
        try:
            orig_class = object.__orig_class__
        except AttributeError:
            raise NoGenericsTypingAvailable()
        annotation = orig_class.__args__[argument_idx]
        conversion = get_dbus_conversion(annotation)
        return cls(conversion=conversion)

    @classmethod
    def from_manual_input(cls, signature: str) -> Self:
        conversion = DbusNativeType(signature)
        return cls(conversion=conversion)


class SignalMapping:
    """
    Represents a mapping of a D-Bus signal to its Python representation.
    """

    __slots__ = ("conversion",)

    def __init__(self, conversion: DbusConvertible):
        self.conversion: DbusConvertible = conversion

    @classmethod
    def from_generics(cls, object, argument_idx: int) -> Self:
        """
        Create a SignalMapping from a generic type annotation.
        The `argument_index` is the index of the type in the generic type.
        """
        try:
            orig_class = object.__orig_class__
        except AttributeError:
            raise NoGenericsTypingAvailable()
        annotation = orig_class.__args__[argument_idx]
        if annotation is type(None):
            conversion = _DbusNone
        else:
            conversion = get_dbus_conversion(annotation)
        return cls(conversion=conversion)

    @classmethod
    def from_manual_input(cls, signature: str) -> Self:
        conversion = DbusNativeType(signature)
        return cls(conversion=conversion)
