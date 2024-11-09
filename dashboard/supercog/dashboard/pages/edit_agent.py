"""The App editor page."""
import reflex as rx

from supercog.dashboard.global_state  import require_google_login
from supercog.dashboard.templates import template
from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.components.agent_page_layout import agent_page_layout

@template(route="/edit/[folder_or_appid]/[[...appid]]", title="Supercog: Edit Agent", image="chat", hide_nav=True,
          on_load=EditorState.editor_page_load)
@require_google_login
def edit_agent() -> rx.Component:
    """
    Returns:
        The UI for the app editor.
    """
    return agent_page_layout(allow_editing=True)
