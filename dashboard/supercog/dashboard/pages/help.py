from pathlib import Path

import reflex as rx


from supercog.dashboard.templates import template
from supercog.dashboard.editor_state import EditorState
from supercog.shared.utils import load_file_content

from supercog.dashboard.components.markdown_modal import markdown_modal
from supercog.dashboard.components.tools_modal import tools_modal

@template(route="/xhelp", title="Supercog: Help", image="circle-help", on_load=EditorState.help_page_load)
def help_page() -> rx.Component:
    """The help page.
    """
    features = load_file_content(tag="CHANGELOG")

    return rx.chakra.box(
        rx.chakra.button("See New Features", color_scheme="purple", on_click=EditorState.toggle_markdown_modal),
        rx.markdown(
            load_file_content(tag="HELP"),
            max_w="50%vw",
        ), 
        markdown_modal("New Features", features),
        max_w="70vw",
        max_h="80vh",
        overflow="scroll",
    )
    

