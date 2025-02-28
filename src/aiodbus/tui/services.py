import logging
from asyncio import Event
from typing import cast

from textual import work
from textual.app import ComposeResult
from textual.logging import TextualHandler
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView

from aiodbus.interface.daemon import FreedesktopDbus

logging.basicConfig(
    level=logging.INFO,
    handlers=[TextualHandler()],
)

logger = logging.getLogger(__name__)


class Service(ListItem):
    service_name: reactive[str] = reactive("")
    is_connected: reactive[bool] = reactive(True, recompose=True)

    def __init__(self, service_name: str):
        super().__init__()
        self.set_reactive(Service.service_name, service_name)

    def compose(self) -> ComposeResult:
        text = self.service_name
        if not self.is_connected:
            text += " (disconnected)"

        yield Label(
            text,
            id="service_name",
            classes="disabled" if not self.is_connected else "",
        )


class Services(Widget):

    class Selected(Message):
        def __init__(self, service_name: str):
            self.service_name = service_name
            super().__init__()

    def __init__(self):
        self._services = list[Service]()
        self._daemon = FreedesktopDbus()
        self._inital_loaded = Event()
        super().__init__()

    async def on_mount(self) -> None:
        self.loading = True
        self._track_services()

    def compose(self) -> ComposeResult:
        yield ListView(*self._services)

    def initial_load(self, names: list[str]):
        names.sort(key=lambda name: name.replace(":", "~"))
        print(names)
        for name in names:
            service = Service(service_name=name)
            self._services.append(service)
        self.query_one(ListView).insert(0, self._services)
        self.loading = False

    def _service_did_appear(self, name: str):
        for service in self._services:
            if service.service_name == name:
                service.is_connected = True
                return
        service = Service(service_name=name)
        self._services.insert(0, service)
        self.query_one(ListView).insert(0, [service])

    def _service_did_disappear(self, name: str):
        for service in self._services:
            if service.service_name == name:
                service.is_connected = False
                return

    def on_list_view_selected(self, message: ListView.Selected) -> None:
        service = cast(Service, message.item)
        self.post_message(self.Selected(service.service_name))

    @work
    async def _track_services(self):
        async with self._daemon.name_owner_changed.catch() as name_owner_changed:
            names = await self._daemon.list_names()
            self._inital_loaded.set()
            self.initial_load(names)

            async for name, old_owner, new_owner in name_owner_changed:
                if old_owner == "":
                    self._service_did_appear(name)
                elif new_owner == "":
                    self._service_did_disappear(name)
