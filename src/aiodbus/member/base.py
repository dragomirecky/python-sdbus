from _sdbus import is_member_name_valid


class DbusMember:
    interface_name: str
    serving_enabled: bool

    @property
    def member_name(self) -> str:
        return self._member_name

    name_requirements = (
        "Member name must only contain ASCII characters, "
        "cannot start with digit, "
        "must not contain dot '.' and be between 1 "
        "and 255 characters in length."
    )

    def __init__(self, member_name: str) -> None:
        self._member_name = member_name

        try:
            assert is_member_name_valid(member_name), (
                f'Invalid name: "{member_name}"; ' f"{self.name_requirements}"
            )
        except NotImplementedError:
            ...
