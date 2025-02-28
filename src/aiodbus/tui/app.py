import logging

from textual.app import App, ComposeResult
from textual.logging import TextualHandler
from textual.screen import Screen
from textual.widgets import TabbedContent, TabPane

from aiodbus import connect
from aiodbus.tui.interfaces import Interfaces
from aiodbus.tui.services import Services

logging.basicConfig(
    level=logging.INFO,
    handlers=[TextualHandler()],
)

logger = logging.getLogger(__name__)


class MainScreen(Screen):
    def __init__(self):
        super().__init__()
        self._service_name_to_pane_id = dict[str, str]()
        self._id_counter = 0

    def on_mount(self) -> None:
        self.query_one(Services).focus()

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("cz.prusa3d.honeybee.StorageManager1", id="debug"):
                yield Interfaces("cz.prusa3d.honeybee.StorageManager1")
            with TabPane("Services", id="services"):
                yield Services()

    def get_next_id(self) -> str:
        self._id_counter += 1
        return f"service_{self._id_counter}"

    async def on_services_selected(self, message: Services.Selected) -> None:
        service_name = message.service_name
        if service_name not in self._service_name_to_pane_id:
            pane_id = self.get_next_id()
            pane = TabPane(service_name, Interfaces(service_name), id=pane_id)
            self._service_name_to_pane_id[service_name] = pane_id
            await self.query_one(TabbedContent).add_pane(pane, after="services")
        else:
            pane_id = self._service_name_to_pane_id[service_name]
        self.query_one(TabbedContent).active = pane_id


class AiodbusApp(App):
    CSS_PATH = "aiodbus.tcss"

    def on_mount(self) -> None:
        connect("session")
        self.push_screen(MainScreen())


if __name__ == "__main__":
    app = AiodbusApp()
    app.run()
