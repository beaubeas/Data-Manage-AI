import reflex as rx
from supercog.dashboard.state_models import UITool
from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.components.tool_icon import tool_icon

markdown_components = {
    "p": lambda text: rx.text(
        text, margin="0",
    ),
}

def delete_button(tool: UITool, show_delete: bool) -> rx.Component:
    return rx.cond(
        show_delete, # & (tool.tool_factory_id != "dynamic_agent_tools"),
        rx.chakra.tooltip(
            rx.icon(
                "trash-2",
                on_click=EditorState.force_remove_uitool(tool.tool_id, tool.tool_factory_id, tool.name),
                size=10,
                flex_shrink="0",
                cursor="pointer",
            ),
            label="Remove Tool",
            cursor="pointer",
        ),
        rx.fragment(),
    ),

def tool_link(tool: UITool, fsize="md", show_delete: bool = False):
    return rx.hstack(
        rx.hstack(
            tool_icon(
                tool_id=tool.tool_factory_id,
                agent_url=tool.agent_url,
                logo_url=tool.logo_url,
            ),
            rx.cond(
                tool.agent_url,
                rx.link(
                    rx.chakra.text(tool.name, font_size=fsize, color="var(--accent-a11)"),
                    href=tool.agent_url,
                    target="_blank",
                ),
                rx.hstack(
                    rx.chakra.text(
                        tool.name,
                        font_size=fsize,
                        cursor="default",
                    ),
                    rx.popover.root(
                        rx.chakra.tooltip(
                            rx.popover.trigger(
                                rx.icon(
                                    "info",
                                    size=10,
                                ),
                                cursor="pointer",
                                flex_shrink="0",
                            ),
                            label="Tool Info"
                        ),
                        rx.popover.content(
                            rx.vstack(
                                rx.text(
                                    "Tool Functions",
                                    font_weight="bold",
                                ),
                                rx.markdown(
                                    tool.functions_help,
                                    component_map=markdown_components,
                                    padding="0",
                                    border="0",
                                    margin="0",
                                ),
                            ),
                        ),
                    ),
                    align="center",
                    spacing="1",
                ),
            ),
        ),
        delete_button(tool, show_delete=show_delete),
        key=tool.name,
        justify="between",
        align="center",
        width="100%",
    ),
