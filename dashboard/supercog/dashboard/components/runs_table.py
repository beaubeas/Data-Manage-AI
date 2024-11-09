import reflex as rx

from supercog.dashboard import styles
from supercog.dashboard.editor_state import EditorState

def render_runs_table_row(run: dict, index: int) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.flex(
                rx.vstack(
                    rx.box(
                        rx.text(
                            run["input"],
                            size="2",
                            width="100%",
                            # Limits summary to three lines, worst case on IE we just show all lines (webkit not supported)
                            class_name="lines-3 webkit-max-lines"
                        ),
                        rx.text(
                            run["time"],
                            size="1",
                            color_scheme="gray",
                            width="100%",
                        ),
                        spacing="1"
                    ),
                ),
                rx.box(
                    rx.chakra.button(
                        rx.icon("trash-2", size=15, stroke_width=1.5),
                        on_click=lambda: EditorState.delete_run(run["id"]).stop_propagation,
                        variant="outline",
                        font_size="0.1em",
                        opacity="0",
                        _group_hover={"opacity": "1"},  # Show on parent hover
                        transition="opacity 0.2s"  # Smooth transition
                    ),
                ),
                spacing="2",
                justify="between",
                width="100%",
            ),
            vertical_align="middle",
            cursor="pointer",
            on_click=lambda: EditorState.click_runlist_cell(index),
            background_color=rx.cond(
                run["id"] == EditorState.active_run_id,
                "var(--chakra-colors-blue-50)",
                "",
            ),
            class_name="!p-2",
            _hover={
                "backgroundColor": "var(--chakra-colors-blue-50)"
            },
            role="group",  
        )
    )

def runs_table(**kwargs) -> rx.Component:
    return rx.vstack(
        rx.chakra.hstack(
            rx.chakra.heading(
                "Agent Runs",
                size="sm"
            ),
            rx.chakra.hstack(
                rx.chakra.tooltip(
                    rx.chakra.button(
                        rx.icon(tag="refresh-cw", size=15),
                        on_click=EditorState.bg_load_runs,
                        size="sm",
                        variant="outline"
                    ),
                    label="Refresh Chats"
                ),
                rx.chakra.tooltip(
                    rx.chakra.button(
                        rx.icon(tag="message-square-plus", size=15),
                        on_click=EditorState.reset_chat,
                        size="sm",
                        variant="outline"
                    ),
                    label="New Chat"
                ),
                justify_content="flex-end",
            ),
            width="100%",
            justify_content="space-between",
        ),
        rx.table.root(
            rx.table.header(),
            rx.table.body(
                rx.foreach(
                    EditorState.agent_runs_ns,
                    lambda run, index: render_runs_table_row(
                        run, index
                    )
                )
            ),
            width="100%",
            overflow_y="auto",
        ),
        width="100%",
        **kwargs,
    )
