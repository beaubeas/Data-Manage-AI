"""The Create Agent page."""
from pathlib import Path
import yaml

from supercog.dashboard.templates import template
from supercog.dashboard.create_agent_state import CreateAgentState

from supercog.dashboard.global_state  import require_google_login
from supercog.dashboard.editor_state import EditorState

import reflex as rx

def example_card(example: dict) -> rx.Component:
    return rx.chakra.card(
        rx.markdown(example["description"]),
        header=rx.link(
            rx.chakra.heading(
                example["name"], 
                size="md", 
                color="blue"
            ), 
            href=f"/edit/{CreateAgentState.current_folder}/new",
        ),
        margin="8px",
    )

### UNUSED 9/9/24 to skip the step of having to choose a type of agent
@template(
        route="/create/[[...folder]]", 
        title="Create Agent", 
        image="add", 
        hide_nav=True)
@require_google_login 
def create_agent() -> rx.Component:
    """
        Start page for creating a new Agent
    """
    new_link = f"/edit/{CreateAgentState.current_folder}/new"
    return rx.chakra.vstack(
        rx.chakra.hstack(
            rx.chakra.heading("Agent Examples", size="sm"),
            rx.chakra.spacer(),
            rx.chakra.link(rx.chakra.button("Create Agent", color_scheme="green"), href=new_link),
            width="100%",
            align_items="flex-end",
        ),
        rx.chakra.responsive_grid(
            rx.foreach(CreateAgentState.examples, example_card),
            columns = [2],
        ),
    )
