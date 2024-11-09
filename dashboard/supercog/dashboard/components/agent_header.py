import reflex as rx

from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.global_state import GlobalState

def model_selector() -> rx.Component:
    return rx.chakra.box(
        rx.chakra.select(
            EditorState.avail_models, 
            value=EditorState.run_model,
            on_change=lambda val: EditorState.change_model(val),
            size="xs",
            border="0",
            focus_border_color="transparent",
        ),
        width="120px",
    )

def open_close_editor_button() -> rx.Component:
    return rx.chakra.tooltip(
        rx.chakra.button(
            rx.cond(
                EditorState.agent_editable,
                rx.icon("panel_left_close", size=20),
                rx.icon("panel_left_open", size=20),
            ),
            on_click=EditorState.toggle_editor_pane,
            padding_inline_start="0.5rem",
            padding_inline_end="0.5rem",
        ),
        label=rx.cond(
            EditorState.agent_editable,
            "Close Editor",
            "Open Editor",
        ),
    )

# TODO: Consolidate these componenets, don't use state, use params
def agent_editable_title() -> rx.Component:
    return rx.chakra.hstack(
        rx.cond(
            ~EditorState.loading_message,
            rx.chakra.hstack(
                rx.chakra.image(
                    src=EditorState.app.avatar,
                    width="var(--chakra-sizes-10)",
                    height="var(--chakra-sizes-10)",
                ),
                rx.debounce_input(
                    rx.chakra.input(
                        value=EditorState.app.name, 
                        on_change=lambda val: EditorState.set_app_value("name", val),
                        placeholder="Agent Name", 
                        width="100%",
                        flex="1",
                    ),
                    debounce_timeout=500,
                ),
                width="100%",
            ),
        ),
        rx.chakra.button(
            "Save", 
            color_scheme="green", 
            is_disabled=rx.cond(EditorState.app_modified, False, True),
            on_click=lambda: EditorState.save_agent,
            margin_right="10px",
        ),
        width="100%",
    )

def agent_title() -> rx.Component:
    return rx.chakra.text(
        EditorState.app.name, 
        font_size="lg", 
        font_weight="bold",
    )

def agent_header(allow_editing: bool) -> rx.Component:
    return rx.chakra.hstack(
        rx.chakra.hstack(
            rx.cond(
                EditorState.agent_editable & allow_editing,
                agent_editable_title(),
                agent_title(),
            ),
            rx.cond(
                allow_editing,
                open_close_editor_button(),
            ),
            align_items="center",
            flex="1",
        ),
        rx.chakra.hstack(
            rx.chakra.tooltip(
                rx.chakra.button(
                    rx.icon("database-zap", size=16), 
                    on_click=EditorState.open_datums_page,
                    variant="outline",
                    font_weight="normal",
                ),
                label="Open Data Browser",
            ),
            rx.cond(
                allow_editing,
                rx.chakra.tooltip(
                    rx.chakra.button(
                        rx.icon("copy",size=16),
                        on_click=EditorState.toggle_app_clone_modal,
                        variant="outline",
                        font_weight="normal",
                    ),
                    label="Copy Agent"
                ),
            ),
            rx.cond(
                allow_editing,
                rx.chakra.tooltip(
                    rx.chakra.button(
                        rx.icon("trash-2",size=16),
                        on_click=GlobalState.toggle_delete_modal('agent', f"agent:{EditorState.app.id}"),
                    ),
                    label="Delete Agent"
                ),
            ),
            model_selector(),
            justify_content="flex-end",
            flex="1",
            
        ),
        width="100%",
        justify_content="space-between",
    )
