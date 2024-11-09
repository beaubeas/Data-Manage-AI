import reflex as rx
from typing import Callable

from supercog.dashboard.state_models import AgentState
from supercog.dashboard.index_state import IndexState

def folder_selector(
        app: AgentState,
        on_change: Callable
    ) -> rx.Component:
    return rx.select.root(
        rx.select.trigger(
            placeholder="Select Folder",
            radius="large",
            variant="surface",
            outline="none",
        ),
        rx.select.content(
            rx.select.group(
                rx.foreach(
                    IndexState.folders_list,
                    lambda folder: rx.select.item(
                        rx.text(folder),
                        value=folder,
                    ),
                ),
            ),
            rx.select.separator(),
            rx.select.item(
                rx.text("No Folder"),
                value="no_folder_key",
            ),
            variant="soft",
        ),
        value=app.folder_name,
        on_change=on_change,
        size="1",
        max_width="140px",
    ),