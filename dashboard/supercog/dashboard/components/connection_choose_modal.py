import functools

import reflex as rx

from supercog.dashboard.global_state import GlobalState
from supercog.dashboard.editor_state import EditorState

def connections_table() -> rx.Component:
    return rx.chakra.table(
        rx.chakra.tbody(
            rx.foreach(
                EditorState.matching_connections,
                lambda cred: rx.chakra.tr(
                    rx.chakra.td(
                        rx.chakra.button(
                            cred.name,
                            on_click=lambda: EditorState.choose_tool_connection(cred.id, cred.name),
                            variant="outline",
                        ),
                    )
                ),
            ),
        ),
    )


def choose_connection_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header("Choose Connection"),
                rx.chakra.modal_body(
                    rx.chakra.heading(
                        "Multiple connections are available for this tool. Please choose one.", 
                        size="sm", 
                        margin_bottom="20px"
                    ),
                    connections_table(),
                ),
                rx.chakra.modal_footer(
                    rx.chakra.button(
                        "Cancel", 
                        on_click=EditorState.toggle_delete_modal('connections', ''),
                    ),
                    justify_content="space-between",
                ),
                min_width="620px",
            ),
        ),
        is_open=GlobalState.open_modals['connections'],
        size="xl",
    )
