from typing import Callable, List, Optional
import functools

import reflex as rx

from supercog.dashboard.state_models import AgentState
from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.state_models import LocalCred, UITool
from supercog.dashboard.components.tool_icon import tool_icon

button_style = {
    "padding": "4px !important",
    "backgroundColor": "#eef2ec",
    "height": "2.5rem",
    "width": "2.5rem",
}

def add_tool_button(tool: UITool, on_click: Optional[Callable] = None) -> rx.Component:
    return rx.chakra.button(
        rx.cond(
            EditorState.uitool_ids.contains(tool.tool_factory_id),
            rx.chakra.icon(tag="check", size="10px", width="10px", height="10px"),
            rx.chakra.icon(tag="add", size="10px", width="10px", height="10px"),
        ),
        width="2.5rem",
        height="2.5rem",
        padding="4px !important",
        on_click=on_click,
        is_disabled=EditorState.uitool_ids.contains(tool.tool_factory_id),
    )

def cred_select_menu_item(cred: LocalCred, uitool: UITool) -> rx.Component:
    return rx.dropdown_menu.item(
        cred.name,
        on_click=functools.partial(EditorState.add_uitool, uitool, cred, True),
    )

def creds_selector(tool: UITool) -> rx.Component:
    return rx.cond(
        # If the length is more than 0 show the list, otherwise just open the modal
        tool.avail_creds.length() > 0,
        rx.dropdown_menu.root(
            rx.dropdown_menu.trigger(
                add_tool_button(tool),
                justify_content="center",
                as_child=True,
            ),
            rx.dropdown_menu.content(
                rx.foreach(
                    tool.avail_creds,
                    lambda cred: cred_select_menu_item(cred, tool)
                ),
                rx.dropdown_menu.item(
                    "New Connection",
                    on_click=EditorState.prompt_for_new_connection(tool.tool_factory_id)
                ),
                variant="soft",
                z_index="var(--chakra-zIndices-popover)",
            ),
        ),
        add_tool_button(tool, on_click=EditorState.prompt_for_new_connection(tool.tool_factory_id)),
    )

markdown_components = {
    "a": lambda text, **props: rx.link(
        text, **props, is_external=True, underline="always", color_scheme="blue", cursor="pointer"
    ),
    "pre": lambda text: rx.text(text),
    "code": lambda text: rx.text(text),
    "codeblock": lambda text, **_props: rx.text(text),
}

def tool_row(tool: UITool) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                tool_icon(
                    tool_id=tool.tool_factory_id,
                    logo_url=tool.logo_url,
                ),
                rx.text(
                    tool.system_name,
                    font_weight="bold",
                    cursor="default",
                ),
                gap="0.5rem",
                align="center",
            ),
            padding_x="4px",
            width="40%",
        ),
        rx.table.cell(
            rx.markdown(
                tool.help,
                component_map=markdown_components,
            ),
            padding_x="4px",
            width="50%",
        ),
        rx.table.cell(
            rx.cond(
                tool.auth_needed,
                creds_selector(tool),
                add_tool_button(tool, on_click=functools.partial(EditorState.add_uitool, tool, {}, True)),
            ),
            justify="center",
            width="2.5rem",
        ),
        align="center",
        color=rx.cond(
            EditorState.uitool_ids.contains(tool.tool_factory_id),
            "var(--gray-10)",
            ""
        ),
    )

def tool_category(category_tools: List) -> rx.Component:
    return rx.chakra.accordion_item(
        rx.chakra.accordion_button(
            rx.chakra.text(category_tools[0]),
            rx.chakra.accordion_icon(),
            justify_content="space-between",
        ),
        rx.chakra.accordion_panel(
            rx.table.root(
                rx.table.body(
                    rx.foreach(
                        category_tools[1],
                        tool_row,
                    ),
                ),
            )
        ),
    )

def tools_library() -> rx.Component:
    return rx.chakra.accordion(
        rx.foreach(
            EditorState.wide_tools_library,
            tool_category,
        ),
        allow_multiple=True,
        allow_toggle=True,
        width="100%",
    ),


def agent_row(app: AgentState) -> rx.Component:
    return rx.chakra.tr(
        rx.chakra.td(
            rx.chakra.hstack(
                rx.chakra.image(
                    src=app.avatar,
                    width="25px",
                    height="25px",
                ),
                rx.cond(
                    app.scope == "private",
                    rx.icon("lock", size=10),
                ),
                width="40px",
            ),
        ),
        rx.chakra.td(
            rx.chakra.tooltip(
                rx.chakra.text(app.name, size="sm"),
                label=app.system_prompt[0:200],
            ),
        ),
        rx.chakra.td(
            rx.chakra.hstack(
                rx.chakra.text("⚡️ " + app.trigger_prefix, font_size="sm"),
                rx.chakra.vstack(
                    rx.chakra.list(
                        rx.foreach(
                            app.tools,
                            lambda tool: rx.chakra.text(tool, font_size="sm"),
                        )
                    ),
                    align_items="stretch",
                    padding_left="20px",
                    height="100%",
                ),
            ),
        ),            
        rx.chakra.td(
            rx.chakra.button(
                "Add",
                variant="solid", 
                padding="4px", 
                color="black", 
                bg="#eef2ec", 
                on_click=EditorState.add_agent_tool(app),
            ),
        ),
    )

def dynamic_icon(icon_name):
    return rx.match(
        icon_name,
        ("folder", rx.icon("folder", style={"margin-right":"2px"})),
        ("folder-tree", rx.icon("folder-tree", style={"margin-right":"2px"})),
    )

def agents_table() -> rx.Component:
    return rx.chakra.table(
        rx.chakra.tbody(
            rx.foreach(
                EditorState.all_agents,
                lambda agent: rx.fragment(
                    rx.cond(
                        agent.is_folder_header,
                        rx.chakra.tr(
                            rx.chakra.td(
                                rx.chakra.hstack(
                                    dynamic_icon(agent.folder_icon_tag),
                                    rx.chakra.text(
                                        rx.cond(
                                            EditorState.expanded_folders.contains(agent.name),
                                            '▼',
                                            '▶'
                                        ),
                                        color="blue",
                                        font_weight="bold",
                                    ),
                                    rx.chakra.text(
                                        agent.name,
                                        color="blue",
                                        font_weight="bold",
                                    ),
                                    spacing="2",
                                    on_click=lambda folder=agent.name: EditorState.toggle_folder(folder),
                                    cursor="pointer",
                                ),
                                colspan="4",
                            )
                        ),
                        rx.cond(
                            EditorState.expanded_folders.contains(agent.folder_name),
                            agent_row(agent),
                            rx.fragment()
                        )
                    )
                )
            )
        )
    )

def tools_modal(open_flag=EditorState.tool_modal_open, close_func=EditorState.toggle_tools_modal) -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header("Agent Tools"),
                rx.chakra.modal_body(
                    rx.chakra.tabs(
                        rx.chakra.tab_list(
                            rx.chakra.tab("Tools"), rx.chakra.tab("Agents"), 
                        ),
                        rx.chakra.tab_panels(
                            rx.chakra.tab_panel(
                                tools_library(),
                            ),
                            rx.chakra.tab_panel(
                                agents_table(),
                            ),
                            max_height="500px",
                            overflow="scroll",
                        ),
                    ),
                ),
                rx.chakra.modal_footer(
                    rx.link(
                        rx.chakra.button(
                            "I Need a Tool", 
                            color_scheme="orange", 
                        ),
                        target="_blank",
                        href="https://github.com/supercog-ai/community/discussions",
                    ),
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Refresh", 
                            #color_scheme="orange", 
                            on_click=EditorState.refresh_tools,
                        ),
                        rx.chakra.button(
                            "Close", 
                            on_click=close_func,
                        ),
                    ),
                    justify_content="space-between",
                ),
                max_width="48rem",
            ),
        ),
        is_open=open_flag,
    )
