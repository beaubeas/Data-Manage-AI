import reflex as rx
from supercog.dashboard.index_state import IndexState
from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.global_state import GlobalState

BUTTON_STYLES = dict(
    bg="#5535d4",
    box_shadow="md",
    px="4",
    py="2",
    h="auto",
    _hover={"bg": "#4c2db3"},
)

def confirm_delete_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.text("Are you sure you want to delete this agent?")
                ),
                rx.chakra.modal_body(
                    rx.chakra.box()
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Yes",
                            style=BUTTON_STYLES,
                            on_click=GlobalState.global_delete_item('agent'),
                        ),
                        rx.chakra.button(
                            "No",
                            style=BUTTON_STYLES,
                            on_click=GlobalState.toggle_delete_modal('agent', ''),
                        ),
                        align_items="space-between",
                    ),
                ),
                bg="#222",
                color="#fff",
            ),
        ),
        is_open=GlobalState.open_modals['agent'],
    )

def confirm_delete_tool_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.text("Are you sure you want to remove this tool?")
                ),
                rx.chakra.modal_body(
                    rx.chakra.box()
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Yes",
                            on_click=EditorState.confirm_remove_uitool,
                            style=BUTTON_STYLES,
                        ),
                        rx.chakra.button(
                            "No",
                            on_click=EditorState.toggle_remove_tool_modal,
                            style=BUTTON_STYLES,
                        ),
                        align_items="space-between",
                    ),
                ),
                bg="#222",
                color="#fff",
            ),
        ),
        is_open=EditorState.remove_tool_modal_open,
    )

def confirm_delete_folder() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.text("Are you sure you want to this folder?")
                ),
                rx.chakra.modal_body(
                    rx.chakra.box()
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Yes",
                            style=BUTTON_STYLES,
                            on_click=GlobalState.global_delete_item('folder'),
                        ),
                        rx.chakra.button(
                            "No",
                            style=BUTTON_STYLES,
                            on_click=GlobalState.toggle_delete_modal('folder', ''),
                        ),
                        align_items="space-between",
                    ),
                ),
                bg="#222",
                color="#fff",
            ),
        ),
        is_open=GlobalState.open_modals['folder'],
    )

def app_clone_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.text("Do you want to make a copy of this agent?")
                ),
                rx.chakra.modal_body(
                    rx.chakra.box(),
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Yes",
                            on_click=EditorState.confirm_app_clone,
                            style=BUTTON_STYLES,
                        ),
                        rx.chakra.button(
                            "No",
                            on_click=EditorState.toggle_app_clone_modal,
                            style=BUTTON_STYLES,
                        ),
                        align_items="space-between",
                    ),
                ),
                bg="#222",
                color="#fff",
            ),
        ),
        is_open=EditorState.app_clone_modal_open,
    )

def create_avatar_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.text("Create an avatar for your agent")
                ),
                rx.chakra.modal_body(
                    rx.chakra.text("Describe your image, or enter a URL"),
                    rx.chakra.vstack(
                        rx.chakra.text_area(
                            value=IndexState.avatar_instructions,
                            on_change=IndexState.set_avatar_instructions,
                        ),
                        rx.cond(
                            IndexState.avatar_generation_error,
                            rx.chakra.alert(
                                rx.chakra.alert_icon(),
                                rx.chakra.alert_title("Error"),
                                rx.chakra.alert_description(IndexState.avatar_generation_error),
                                status="error",
                            ),
                        ),
                    ),
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Generate",
                            is_loading=IndexState.avatar_generating,
                            on_click=IndexState.generate_avatar,
                            style=BUTTON_STYLES,
                        ),
                        rx.chakra.button(
                            "Cancel",
                            on_click=lambda: IndexState.toggle_avatar_modal,
                            style=BUTTON_STYLES,
                        ),
                        align_items="space-between",
                    ),
                ),
                bg="#222",
                color="#fff",
            ),
        ),
        is_open=IndexState.avatar_modal_open,
    )

def reflect_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.hstack(
                        rx.chakra.text("Learning"),
                        rx.chakra.spacer(),
                        rx.chakra.box(
                            rx.cond(
                                EditorState.reflect_modal_total_tokens > 0,
                                rx.chakra.vstack(
                                    rx.chakra.text(
                                        f"Tokens: {EditorState.reflect_modal_total_tokens:,}",
                                        font_size="sm",
                                        color="gray.500",
                                    ),
                                    rx.chakra.text(
                                        EditorState.reflection_cost,
                                        font_size="sm",
                                        color="gray.500",
                                    ),
                                    align_items="flex-end",
                                ),
                            ),
                        ),
                    ),
                ),
                rx.chakra.modal_body(
                    rx.chakra.vstack(
                        # Facts section
                        rx.foreach(
                            EditorState.reflect_modal_result,
                            lambda item, i: rx.chakra.hstack(
                                rx.chakra.checkbox(
                                    "",
                                    is_checked=EditorState.reflect_modal_checked[i],
                                    on_change=lambda _: EditorState.toggle_reflect_modal_checkbox(i),
                                    margin_right="8px",
                                ),
                                rx.chakra.text(
                                    item,
                                    flex="1",
                                ),
                                border="1px solid #e2e8f0",
                                padding="8px",
                                border_radius="4px",
                                width="100%",
                                background="white",
                            )
                        ),
                        # Analysis section in accordion
                        rx.cond(
                            EditorState.reflect_modal_analysis != "",
                            rx.chakra.accordion(
                                rx.chakra.accordion_item(
                                    rx.chakra.accordion_button(
                                        rx.chakra.heading(
                                            "Analysis",
                                            size="sm",
                                        ),
                                        rx.chakra.accordion_icon(),
                                    ),
                                    rx.chakra.accordion_panel(
                                        rx.markdown(
                                            EditorState.reflect_modal_analysis
                                        ),
                                        bg="gray.50",
                                        border_radius="md",
                                        p=4,
                                    ),
                                ),
                                allow_toggle=True,
                                width="100%",
                                mt=4,
                            ),
                        ),
                        spacing="4",
                        width="100%",
                    ),
                ),
                rx.chakra.modal_footer(
                    rx.chakra.button(
                        "Cancel",
                        on_click=EditorState.close_reflect_modal,
                    ),
                    rx.chakra.button(
                        "Save",
                        color_scheme="blue",
                        on_click=EditorState.save_reflect_modal
                    ),
                    justify_content="space-between", 
                ),
                background="white",
                color="black",
                min_width="620px",
            ),
        ),
        is_open=EditorState.reflect_modal_open,
        size="xl",
    )

def new_folder_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.text("Create/edit a folder")
                ),
                rx.chakra.modal_body(
                    rx.chakra.input(
                        value=GlobalState.new_folder_name,
                        on_change=GlobalState.set_new_folder_name,
                    )
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.checkbox(
                            "Shared",
                            is_checked=GlobalState.is_folder_shared,
                            on_change=GlobalState.set_is_folder_shared,
                        ),
                        rx.chakra.spacer(),
                        rx.chakra.button(
                            "Save",
                            on_click=GlobalState.create_new_folder,
                            style=BUTTON_STYLES,
                        ),
                        rx.chakra.button(
                            "Cancel",
                            on_click=GlobalState.toggle_new_folder_modal,
                            style=BUTTON_STYLES,
                        ),
                        align_items="center",
                        width="100%",
                    ),
                ),
                bg="#222",
                color="#fff",
            ),
        ),
        is_open=GlobalState.new_folder_modal_open,
    )

# 10/14/24 No longer used
# def error_popup_modal() -> rx.Component:
#     return rx.chakra.modal(
#         rx.chakra.modal_overlay(
#             rx.chakra.modal_content(
#                 rx.chakra.modal_header(
#                     rx.chakra.text("Unexpect error")
#                 ),
#                 rx.chakra.modal_body(
#                     rx.markdown(EditorState.error_message),
#                     width="500px",
#                 ),
#                 rx.chakra.modal_footer(
#                     rx.chakra.hstack(
#                         rx.chakra.button(
#                             "Close",
#                             on_click=EditorState.toggle_delete_modal('error', ''),
#                             style=BUTTON_STYLES,
#                         ),
#                         align_items="space-between",
#                     ),
#                 ),
#                 bg="#222",
#                 color="#fff",
#                 min_width="510px",
#             ),
#         ),
#         is_open=EditorState.open_modals['error'],
#     )
