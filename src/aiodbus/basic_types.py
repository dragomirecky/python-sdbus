from typing import Any

DbusBasicType = str | int | bytes | float | Any
DbusStructType = tuple[DbusBasicType, ...]
DbusDictType = dict[DbusBasicType, DbusBasicType]
DbusVariantType = tuple[str, DbusStructType]
DbusArrayType = list[DbusBasicType]
DbusCompleteType = DbusBasicType | DbusStructType | DbusDictType | DbusVariantType | DbusArrayType
DbusCompleteTypes = tuple[DbusCompleteType, ...]
