from typing import Annotated

from aiodbus.signature import MethodMapping, WithConversion, WithName


def no_param_return_none() -> None: ...


def no_param_return_empty_tuple(): ...


def int_param_return_int(x: int) -> int: ...


def two_simple_params_return_two_simple_types(x: int, y: str) -> tuple[int, str]: ...


def complex_input_with_builtin_types(x: dict[str, list[tuple[int, str, float]]]): ...


def single_result() -> int: ...


def multiple_result_values() -> tuple[int, str]: ...


def complex_result_type() -> tuple[int, str, dict[str, list[tuple[int, str, float]]]]: ...


def simple_call_with_name_hint(unused_name: Annotated[int, WithName("x")]) -> int: ...


class MyObject:
    def __init__(self, value: int):
        self.value = value


class MyObjectDbusConversion:
    """
    Testing mapping to dbus; sends the value of the object as string, instead of int.
    """

    signature = "s"

    def to_dbus(self, value: MyObject) -> str:
        return str(value.value)

    def from_dbus(self, value: str) -> MyObject:
        assert isinstance(value, str), "Expected the value to be a string"
        return MyObject(int(value))


def send_my_object(obj: Annotated[MyObject, WithConversion(MyObjectDbusConversion())]) -> None: ...


def receive_my_object() -> Annotated[MyObject, WithConversion(MyObjectDbusConversion())]: ...


class SomeObject:
    def with_method(self, x: int) -> int: ...


class MyObjectCompound:
    def __init__(self, value_a: int, value_b: str):
        self.value_a = value_a
        self.value_b = value_b


class MyObjectCompoundDbusConversion:
    signature = "(is)"

    def to_dbus(self, value: MyObjectCompound):
        return (value.value_a, value.value_b)

    def from_dbus(self, value: tuple[int, str]) -> MyObjectCompound:
        assert len(value) == 2, "Expected a tuple with two values"
        assert isinstance(value[0], int), "Expected the first value to be an int"
        assert isinstance(value[1], str), "Expected the second value to be a string"
        return MyObjectCompound(value[0], value[1])


def receive_my_object_compound() -> (
    Annotated[MyObjectCompound, WithConversion(MyObjectCompoundDbusConversion())]
): ...


def receive_two_my_compound_objects() -> tuple[
    Annotated[
        MyObjectCompound,
        WithConversion(MyObjectCompoundDbusConversion()),
        WithName("result_object"),
    ],
    Annotated[MyObjectCompound, WithConversion(MyObjectCompoundDbusConversion())],
]: ...


class TestSignatureDeduction:
    def test_no_param_return_none(self):
        method = MethodMapping.from_callable(no_param_return_none)
        assert method.input_params == []
        assert method.input_conversion.signature == ""
        assert method.result_conversion.signature == ""

    def test_int_param_return_int(self):
        method = MethodMapping.from_callable(int_param_return_int)
        assert method.input_params[0].name == "x"
        assert method.input_conversion.signature == "i"
        assert method.result_conversion.signature == "i"

    def test_two_simple_params_return_two_simple_types(self):
        method = MethodMapping.from_callable(two_simple_params_return_two_simple_types)
        assert method.input_params[0].name == "x"
        assert method.input_params[1].name == "y"
        assert method.input_conversion.signature == "is"
        assert method.result_conversion.signature == "is"

    def test_complex_input_with_builtin_types(self):
        method = MethodMapping.from_callable(complex_input_with_builtin_types)
        assert method.input_params[0].name == "x"
        assert method.input_conversion.signature == "a{sa(isd)}"

    def test_single_result(self):
        method = MethodMapping.from_callable(single_result)
        assert method.input_conversion.signature == ""
        assert method.result_conversion.signature == "i"

    def test_multiple_result_values(self):
        method = MethodMapping.from_callable(multiple_result_values)
        assert method.input_conversion.signature == ""
        assert method.result_conversion.signature == "is"

    def test_complex_result_type(self):
        method = MethodMapping.from_callable(complex_result_type)
        assert method.input_conversion.signature == ""
        assert method.result_conversion.signature == "isa{sa(isd)}"

    def test_signature_with_nonbuiltin_type(self):
        method = MethodMapping.from_callable(send_my_object)
        assert method.input_conversion.signature == "s"

    def test_signature_with_nonbuiltin_type_receive(self):
        method = MethodMapping.from_callable(receive_my_object)
        assert method.result_conversion.signature == "s"

    def test_signature_with_compound_object(self):
        method = MethodMapping.from_callable(receive_my_object_compound)
        assert method.result_conversion.signature == "(is)"

    def test_result_names_with_hint(self):
        method = MethodMapping.from_callable(receive_two_my_compound_objects)
        assert len(method.input_params) == 0
        assert len(method.result_params) == 2
        assert method.result_params[0].name == "result_object"
        assert method.result_params[1].name == "out_2"

    def test_result_names_without_hint(self):
        method = MethodMapping.from_callable(receive_my_object)
        assert len(method.result_params) == 1
        assert method.result_params[0].name == "out"

    def test_input_names_without_hint(self):
        method = MethodMapping.from_callable(simple_call_with_name_hint)
        assert len(method.input_params) == 1
        assert method.input_params[0].name == "x"

    def test_ignores_self_param_on_unbound_method(self):
        method = MethodMapping.from_callable(SomeObject.with_method)
        assert len(method.input_params) == 1


class TestDataConversion:
    def test_empty_tuple_as_result(self):
        method_without_return_type = MethodMapping.from_callable(no_param_return_empty_tuple)
        assert method_without_return_type.result_conversion.signature == ""
        assert method_without_return_type.result_conversion.from_dbus(()) == None
        assert method_without_return_type.result_conversion.to_dbus(None) == ()

    def test_simple_argument_conversion(self):
        method = MethodMapping.from_callable(int_param_return_int)
        assert method.input_conversion.from_dbus((42,)) == (42,)
        assert method.input_conversion.to_dbus((42,)) == (42,)

    def test_two_simple_params_conversion(self):
        method = MethodMapping.from_callable(two_simple_params_return_two_simple_types)
        assert method.input_conversion.from_dbus((42, "test")) == (42, "test")
        assert method.input_conversion.to_dbus((42, "test")) == (42, "test")

    def test_complex_input_conversion(self):
        method = MethodMapping.from_callable(complex_input_with_builtin_types)
        input_data = ({"key1": [("a", "b", 1.0), ("c", "d", 2.0)], "key2": [("e", "f", 3.0)]},)
        dbus_data = method.input_conversion.to_dbus(input_data)
        assert dbus_data == (
            {"key1": [("a", "b", 1.0), ("c", "d", 2.0)], "key2": [("e", "f", 3.0)]},
        )
        assert method.input_conversion.from_dbus(dbus_data) == input_data

    def test_send_to_dbus_custom_object(self):
        obj = MyObject(42)
        method = MethodMapping.from_callable(send_my_object)
        dbus_data = method.input_conversion.to_dbus((obj,))
        assert dbus_data == ("42",)

    def test_method_result_for_none(self):
        method = MethodMapping.from_callable(no_param_return_none)
        dbus_data = method.result_conversion.to_dbus(None)
        assert dbus_data == ()
        python_result = method.result_conversion.from_dbus(dbus_data)
        assert python_result is None

    def test_method_result_for_single_value(self):
        method = MethodMapping.from_callable(single_result)
        dbus_data = method.result_conversion.to_dbus(42)
        assert dbus_data == (42,)
        python_result = method.result_conversion.from_dbus(dbus_data)
        assert python_result == 42

    def test_method_result_for_multiple_values(self):
        method = MethodMapping.from_callable(multiple_result_values)
        dbus_data = method.result_conversion.to_dbus((42, "test"))
        assert dbus_data == (42, "test")
        python_result = method.result_conversion.from_dbus(dbus_data)
        assert python_result == (42, "test")

    def test_receive_from_dbus_custom_object(self):
        method = MethodMapping.from_callable(receive_my_object)
        dbus_data = ("42",)
        obj = method.result_conversion.from_dbus(dbus_data)
        assert isinstance(obj, MyObject)
        assert obj.value == 42

    def test_receive_from_dbus_custom_object_compound(self):
        method = MethodMapping.from_callable(receive_my_object_compound)
        dbus_data = ((42, "MyObject"),)
        obj = method.result_conversion.from_dbus(dbus_data)
        assert isinstance(obj, MyObjectCompound)
        assert obj.value_a == 42
        assert obj.value_b == "MyObject"
