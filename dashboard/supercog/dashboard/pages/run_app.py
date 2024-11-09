"""The App view page."""
from supercog.dashboard.templates import template
from supercog.dashboard.editor_state import EditorState

from supercog.dashboard.components.agent_page_layout import agent_page_layout

import reflex as rx

@template(route="/app/[appid]/", title="Supercog: Run Agent", image="play-circle", hide_nav=True,
          on_load=EditorState.app_run_page_load)
def run_app() -> rx.Component:
    """
    Returns:
        The UI for the app editor.
    """
    return agent_page_layout(allow_editing=False)
        
