from _sdbus import is_member_name_valid
from aiodbus.dbus_common_funcs import _method_name_converter


class DbusMember:
    interface_name: str
    serving_enabled: bool

    @property
    def name(self) -> str:
        try:
            return self._name
        except AttributeError:
            raise RuntimeError("Member name not set")

    name_requirements = (
        "Member name must only contain ASCII characters, "
        "cannot start with digit, "
        "must not contain dot '.' and be between 1 "
        "and 255 characters in length."
    )

    def __init__(self, name: str | None) -> None:
        if name is not None:
            self._set_name(name)

    def __set_name__(self, owner: object, name: str) -> None:
        if not hasattr(owner, "_name"):
            name = "".join(_method_name_converter(name))
            self._set_name(name)

    def _set_name(self, name: str) -> None:
        try:
            assert is_member_name_valid(name), (
                f'Invalid name: "{name}"; ' f"{self.name_requirements}"
            )
        except NotImplementedError:
            ...
        self._name = name
