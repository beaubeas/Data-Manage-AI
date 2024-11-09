"""The App view page."""
from supercog.dashboard.templates import template
from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.components.agent_page_layout import agent_page_layout

from supercog.dashboard.global_state  import require_google_login

import reflex as rx

@template(route="/supercog/", title="Supercog: Home", image="play-circle", hide_nav=True,
          on_load=EditorState.supercog_page_load)
@require_google_login
def supercog_page() -> rx.Component:
    """
    Returns:
        The Supercog default home experience
    """
    return agent_page_layout(allow_editing=False)
