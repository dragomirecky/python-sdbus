from _sdbus import SdBus, SdBusError
from aiodbus.exceptions import (
    DbusError,
    SdBusRequestNameAlreadyOwnerError,
    SdBusRequestNameExistsError,
    SdBusRequestNameInQueueError,
)

original_request_name = SdBus.request_name


async def request_name(self, name: str, flags: int, /) -> None:
    try:
        response = await original_request_name(self, name, flags)
    except SdBusError as e:
        raise DbusError(e) from e

    result = response.get_contents()
    if result == 1:  # Success
        return
    elif result == 2:  # Reply In Queue
        raise SdBusRequestNameInQueueError()
    elif result == 3:
        raise SdBusRequestNameExistsError()
    elif result == 4:
        raise SdBusRequestNameAlreadyOwnerError()
    else:
        raise DbusError(f"Unknown result code: {result}")


SdBus.request_name = request_name  # type: ignore
