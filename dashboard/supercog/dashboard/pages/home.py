"""The Home page."""
import pandas as pd
import reflex as rx

from supercog.dashboard.global_state  import require_google_login

from supercog.dashboard.components.buttons import link_button
from supercog.dashboard.components.folder_nav import folder_nav
from supercog.dashboard.components.tool_icon import tool_icon
from supercog.dashboard.templates import template
from supercog.dashboard.global_state import GlobalState
from supercog.dashboard.index_state import IndexState
from supercog.dashboard.state_models import TemplateState
from supercog.dashboard.components.modal import new_folder_modal, create_avatar_modal, confirm_delete_modal

from .index import agent_table


def agent_card(template: TemplateState) -> rx.Component:
    return rx.hover_card.root(
        rx.hover_card.trigger(
            rx.card(
                rx.chakra.vstack(
                    rx.chakra.hstack(
                        rx.chakra.image(
                            src=template.avatar_url,
                            class_name="w-[40px] h-[40px] lg:w-[50px] lg:h-[50px]"
                        ),
                        rx.chakra.text(
                            template.name, 
                            font_size="lg", 
                            font_weight="bold",
                        ),
                    ),
                    rx.box(
                        rx.chakra.text(
                            template.welcome_message,
                            class_name="webkit-max-lines lines-4"
                        ),
                        width="100%",
                    ),
                    align_items="flex-start",
                    margin_inline_start="0 !important",
                ),
                class_name="starter-card max-w-full xs:max-w-[220px]",
                on_click=IndexState.goto_edit_app(template.id),
                as_child=True,
            )
        ),
        rx.hover_card.content(
            rx.chakra.vstack(
                rx.chakra.text("Tools", font_weight="bold", text_align="start"),
                rx.foreach(
                    template.tools,
                    lambda tool: rx.chakra.hstack(
                        tool_icon(
                            tool_id=tool.tool_factory_id,
                            logo_url=tool.logo_url,
                        ),
                        rx.chakra.text(tool.name, class_name="!mt-0"),
                        gap="0.5rem",
                    ),
                ),
                align_items="start"
            ),
        ),
    )

def learning_block() -> rx.Component:
    return rx.box(
        rx.chakra.heading("Learn", size="md", padding_bottom="20px"),
        rx.hstack(
            link_button(
                icon=rx.icon("book-open", size=20),
                text="Help Docs",
                href="https://github.com/supercog-ai/community/wiki",
                external_link=True,
            ),
            link_button(
                icon=rx.icon("youtube", size=20),
                text="Videos",
                href="https://www.youtube.com/@supercog-ai",
                external_link=True,
            ),
            link_button(
                icon=rx.icon("waypoints", size=20),
                text="LLM Models Support",
                href="https://github.com/supercog-ai/community/wiki/LLM-Models",
                external_link=True,
            ),
        ),
        class_name="px-5 mb-5"
    )

def getstarted_block() -> rx.Component:
    return rx.cond(
        IndexState.system_agent_templates & IndexState.system_agent_templates.length() > 0,
        rx.box(
            rx.chakra.heading("Get Started", size="md", padding_bottom="20px"),
            rx.grid(
                rx.foreach(
                    IndexState.system_agent_templates,
                    agent_card,
                ),
                flow="row",
                justify="between",
                spacing="4",
                width="100%",
                class_name="grid-cols-1 xs:grid-cols-2 md:grid-cols-3 lg:grid-cols-5",
            ),
            padding="20px",
            margin_bottom="20px",
        ),
    )

def recent_agents_block() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.chakra.heading("Recent Agents", size="md"),
            rx.cond(
                IndexState.recent_agent_list.length() > 0,
                rx.hstack(
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
                        href=f"/edit/new",
                    ),
                ), 
            ),
            width="100%",
            align="center",
            justify="between"
        ),
        rx.cond(
            IndexState.recent_agent_list.length() == 0,
            rx.chakra.link(
                rx.chakra.button(
                    "Create Your Own Agent", 
                    color_scheme="blue",
                ),
                href=f"/edit/new",
            ),
        ),
        agent_table(IndexState.recent_agent_list, agent_list_type="recent"),
        padding="20px",
        margin_bottom="20px",
        gap="2rem",
        class_name="w-full xl:w-[80%]",
    )

def folders_block() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.chakra.heading("Folders", size="md"),
            rx.chakra.button(
                "New Folder",
                on_click=GlobalState.toggle_new_folder_modal,
            ),
            width="100%",
            align="center",
            justify="between",
        ),
        folder_nav(),
        padding="20px",
        margin_bottom="20px",
        gap="2rem",
        class_name="w-full xl:w-[80%]",
    )

def toolbar() -> rx.Component:
    return rx.chakra.hstack(
        rx.chakra.spacer(),
        rx.upload(
            rx.chakra.button(rx.icon("upload", size=15), variant="outline"),
            id="upload2",
            accept = {
                "application/yaml": [".yaml"],
                "application/b64": [".b64"],
            },
            on_drop=IndexState.handle_upload_agent(rx.upload_files(upload_id="upload2")),
        ),
        padding_bottom="10px",
        width="100%",
        align_items="flex-end",
    )

@template(route="/home", title="Supercog: Home", image="home", on_load=IndexState.home_page_load)
@require_google_login
def home_page() -> rx.Component:
    """The Home page.
    """
    return rx.chakra.vstack(
        learning_block(),
        getstarted_block(),
        folders_block(),
        recent_agents_block(),
        new_folder_modal(),
        create_avatar_modal(),
        confirm_delete_modal(),
        align_items="flex-start",
    )
