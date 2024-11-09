"""The home page of the app."""
from typing import Literal

from supercog.dashboard.components.folder_selector import folder_selector
from supercog.dashboard.state_models import AgentState
from supercog.dashboard.index_state import IndexState
from supercog.dashboard.global_state import GlobalState


import reflex as rx

def agent_row(app: AgentState, agent_list_type: Literal["all", "recent", "folder"]) ->  rx.Component:
    # Have an image cell, name cell, folder cell, and tools cell
    return rx.table.row(
        rx.table.cell(
            rx.chakra.image(
                src=app.avatar,
                width="50px",
                height="50px",
            ),
            on_click=lambda: IndexState.toggle_avatar_modal(app.id),
            cursor="pointer",
            width="50px",
        ),
        rx.table.cell(
            rx.chakra.vstack(
                rx.hover_card.root(
                    rx.hover_card.trigger(
                        rx.chakra.link(
                            app.name, 
                            on_click=IndexState.goto_edit_app(app.id, app.folder_name),
                            font_size="lg", 
                            font_weight="bold",
                            margin_left="0.5rem",
                        ),
                    ),
                    rx.hover_card.content(
                        rx.chakra.text_area(
                            app.system_prompt,
                            width="400px",
                            height="220px",
                            max_height="220px",
                            is_read_only=True,
                            padding="0",
                            border="0",
                        ),
                    ),
                ),
                rx.chakra.text(app.description),
                align_items="flex-start",
            ),
        ),
        rx.table.cell(
            folder_selector(
                app,
                on_change=lambda val: IndexState.set_folder_for_agent(app.id, val, agent_list_type),
            )
        ),
        rx.table.cell(
            rx.chakra.vstack(
                rx.cond(
                    app.trigger_prefix != "Chat box",
                    rx.chakra.text("⚡️ " + app.trigger_prefix, font_size="sm"),
                ),
                rx.chakra.list(
                    rx.foreach(
                        app.uitools,
                        lambda tool: rx.chakra.text(tool.name, font_size="sm"),
                    )
                ),
                align_items="stretch",
            ),
        ),
        rx.table.cell(
            rx.chakra.button(
                rx.icon("trash-2",size=16),
                on_click=GlobalState.toggle_delete_modal('agent', f"agent:{app.id}"),
            ),
        ),
        align="center",
    )

def agent_table(agents: list[AgentState], agent_list_type: Literal["all", "recent", "folder"]) -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Agent", padding_x="2px"),
                rx.table.column_header_cell("", padding_x="2px"),
                rx.table.column_header_cell("Folder", padding_x="2px"),
                rx.table.column_header_cell("Tools Used", padding_x="2px"),
                rx.table.column_header_cell("", padding_x="2px"),
            ),
        ),
        rx.table.body(
            rx.foreach(
                agents,
                lambda agent: agent_row(agent, agent_list_type)
            )
        ),
        width="100%",
    )
