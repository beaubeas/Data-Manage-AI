import reflex as rx

from supercog.dashboard import styles
from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.components.folder_selector import folder_selector
from supercog.dashboard.components.agent_header import agent_header
from supercog.dashboard.components.connection_choose_modal import choose_connection_modal
from supercog.dashboard.components.editing_sidebar import editing_sidebar
from supercog.dashboard.components.runs_table import runs_table
from supercog.dashboard.components.tools_sidebar import tools_sidebar

from supercog.dashboard.components.chat import chat
from supercog.dashboard.components.modal import (
    confirm_delete_modal, 
    confirm_delete_tool_modal,
    app_clone_modal,
    reflect_modal
)
from supercog.dashboard.components.tools_modal import tools_modal

# Pull in the Connections modal so we can create new Connections needed for new tools
# added while editing the Agent.
from supercog.dashboard.connections_state import ConnectionsState
from supercog.dashboard.pages.connections import connection_modal

# Have to build two separate breadcrumbs depending on if there is a folder or not
# For some reason the cond does not work on breadcrumb items
def agent_page_breadcrumb_and_folder_selector(app) -> rx.Component:
    return rx.hstack(
            rx.cond(
            app.folder_name,
            rx.chakra.breadcrumb(
                rx.chakra.breadcrumb_item(
                    rx.chakra.breadcrumb_link("Home", href=f"/home"),
                    color="blue.500"
                ),
                rx.chakra.breadcrumb_item(
                    rx.chakra.breadcrumb_link(f"{app.folder_name}", href=f"/agents/{app.folder_slug}"),
                    color="blue.500"
                ),
                rx.chakra.breadcrumb_item(
                    rx.chakra.breadcrumb_link(
                        f"{app.name}",
                        is_current_page=True,
                        style={
                            "cursor": "default !important",
                            "textDecoration": "none",
                        }
                    ),
                ),
            ),
            rx.chakra.breadcrumb(
                rx.chakra.breadcrumb_item(
                    rx.chakra.breadcrumb_link("Home", href=f"/home"),
                    color="blue.500"
                ),
                rx.chakra.breadcrumb_item(
                    rx.chakra.breadcrumb_link(
                        f"{app.name}",
                        is_current_page=True,
                        style={
                            "cursor": "default !important",
                            "textDecoration": "none",
                        }
                    ),
                ),
            ),
        ),
        rx.cond(
            EditorState.agent_editable,
            rx.fragment(
                folder_selector(
                    EditorState.app,
                    on_change=EditorState.set_folder,
                )
            ),
        ),
        align="center",
        width="100%",
    ),

def agent_page_layout(allow_editing: bool) -> rx.Component:
    return rx.chakra.vstack(
        agent_page_breadcrumb_and_folder_selector(EditorState.app),
        agent_header(allow_editing=allow_editing),
        # Editor page body, with Editor pane on the left and chat box on the right
        rx.chakra.hstack(
            rx.cond(
                EditorState.agent_editable & allow_editing,
                rx.box( # Have to have a box wrapper because reflex throws an error if the conditional args aren't BaseComponents
                    editing_sidebar(),
                    flex="20",
                    height="100%",
                ),
                runs_table(max_width="200px", max_height= styles.chat_height, flex="5"),
            ),
            chat(flex="20"),
            rx.cond(
                ~(EditorState.agent_editable & allow_editing),
                tools_sidebar(max_width="200px", flex="5"),
            ),
            align_items="stretch",
            width="100%",
            height="calc(100% - var(--chakra-sizes-10) - 2rem - 24px)", # Subtract the breadcrumbs, header, and gaps
            flex="1",
            id="app_and_run_box",
        ),
        tools_modal(),
        confirm_delete_modal(),
        confirm_delete_tool_modal(),
        app_clone_modal(),
        reflect_modal(),
        connection_modal(ConnectionsState.new_cred),
        choose_connection_modal(),
        rx.script(src="/custom.js"), 
        bg=styles.bg_dark_color,
        color=styles.text_light_color,
        width="100%",
        height="100%",
        id="edit-app",
        spacing="0",
        class_name="edge_bleed",
        gap="1rem",
    )
