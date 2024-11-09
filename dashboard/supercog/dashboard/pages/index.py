"""The home page of the app."""
from supercog.dashboard import styles
from supercog.dashboard.templates import template
from supercog.dashboard.global_state  import require_google_login

from supercog.dashboard.index_state import IndexState

from supercog.dashboard.components.modal import new_folder_modal, create_avatar_modal, confirm_delete_modal
from supercog.dashboard.components.agent_table import agent_table

import reflex as rx

def default_agents_list() -> rx.Component:
    return rx.fragment(
        rx.chakra.vstack(
            rx.cond(
                IndexState.current_folder == "recent",
                agent_table(IndexState.recent_agent_list, "recent"),
                agent_table(IndexState.folder_agent_list, "folder"),
            ),
            width="100%",
            align_items="stretch",
        ),
    )

@template(route="/agents/[[...folder]]", title="Supercog: Home", image="home", on_load=IndexState.index_page_load, hide_nav=True)
@require_google_login
def index() -> rx.Component:
    """The home page.

    Returns:
        The UI for the home page.
    """
    create_link = f"/edit/{IndexState.current_folder}/new"
    return rx.chakra.vstack(
        rx.hstack(
            rx.cond(
                IndexState.current_folder_name,
                rx.chakra.breadcrumb(
                    rx.chakra.breadcrumb_item(
                        rx.chakra.breadcrumb_link("Home", href=f"/home"),
                        color="blue.500",
                    ),
                    rx.chakra.breadcrumb_item(
                        rx.chakra.breadcrumb_link(
                            f"{IndexState.current_folder_name}",
                            is_current_page=True,
                            style={
                                "cursor": "default !important",
                                "textDecoration": "none",
                            }
                        )
                    ),
                    
                ),
            ),
            rx.chakra.spacer(),
            rx.upload(
                rx.chakra.tooltip(
                    rx.chakra.button(rx.icon("upload", size=16), variant="outline"),
                    label="Upload Agent"
                ),
                id="upload_agent",
                accept = {
                    "application/yaml": [".yaml"],
                    "application/b64": [".b64"],
                },
                on_drop=IndexState.handle_upload_agent(rx.upload_files(upload_id="upload_agent")),
            ),
            rx.chakra.link(
                rx.chakra.button(
                    "New Agent",
                    color_scheme="blue",
                ),
                href=create_link
            ),
            padding_bottom="10px",
            width="100%",
            align_items="flex-end",
        ),
        rx.cond(
            IndexState.recent_agent_list.length() > 0,
            rx.chakra.heading("Recent", size="md"),
        ),
        default_agents_list(),
        new_folder_modal(),
        confirm_delete_modal(),
        create_avatar_modal(),
        bg=styles.bg_dark_color,
        color=styles.text_light_color,
        min_h="90vh",
        #max_height="87vh",
        align_items="stretch",
        width="100%",
        spacing="0",
    )
