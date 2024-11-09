import reflex as rx

from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.components.tool_link import tool_link
from supercog.dashboard.components.accordion_item import accordion_item

def file_item(file: dict[str, str]) -> rx.Component:
    return rx.hstack(
        rx.chakra.link(
            file["name"],
            on_click=EditorState.view_single_datum(file["name"]),
            overflow="hidden",
            text_overflow="ellipsis",
            text_wrap="nowrap",
        ),
        rx.dropdown_menu.root(
            rx.dropdown_menu.trigger(
                rx.icon(
                    "ellipsis-vertical",
                    size=15,
                    flex_shrink="0",
                ),
                cursor="pointer",
            ),
            rx.dropdown_menu.content(
                rx.dropdown_menu.item(
                    "Preview",
                    on_click=EditorState.view_single_datum(file["name"]),
                ),
                rx.dropdown_menu.item(
                    "Download",
                    on_click=EditorState.download_file(file["name"]),
                ),
                rx.dropdown_menu.item(
                    "Delete",
                    on_click=EditorState.delete_file(file["name"]),
                    color_scheme="red"
                ),
                variant="soft",
            ),
        ),
        width="100%",
        align="center",
        justify="between",
    )

def tools_sidebar(**kwargs) -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.text(
            "Tools", 
            font_weight="bold", 
            font_size="md", 
            text_decoration="underline"
        ),
        rx.foreach(
            EditorState.run_tools,
            lambda tool: rx.fragment(
                tool_link(tool, fsize="xs", show_delete=EditorState.is_supercog_agent),
                key=tool.name
            ),
        ),
        rx.chakra.button("Add Tool", on_click=EditorState.toggle_tools_modal),
        rx.chakra.accordion(
            accordion_item(
                show_border=True,
                header=rx.fragment(
                    rx.chakra.text(
                        "Files & Data", 
                        size="sm", 
                        font_weight="bold", 
                        text_decoration="underline"
                    ),
                    rx.chakra.accordion_icon(),
                ),
                content=rx.vstack(
                    rx.chakra.hstack(
                        rx.chakra.tooltip(
                            rx.chakra.button(
                                rx.icon(tag="refresh-cw", size=15),
                                on_click=EditorState.refresh_data_list,
                                size="sm",
                                variant="outline",
                            ),
                            label="Refresh File List"
                        ),
                        rx.upload(
                            rx.chakra.tooltip(
                                rx.chakra.button(
                                    rx.icon("upload", size=15),
                                    size="sm",
                                    variant="outline"
                                ),
                                label="Upload Files"
                            ),
                            on_drop=EditorState.tray_file_upload(rx.upload_files(upload_id="tray_upload")),
                            id="tray_upload",
                            border="1px dotted rgb(107,99,246)",
                            padding="0",
                        ),
                    ),
                    rx.foreach(
                        EditorState.files_list,
                        file_item,
                    ),
                ),
                header_kwargs={
                    "padding": "0"
                },
            ),
            allow_toggle=True,
        ),
        align_items="stretch",
        padding_left="3px",
        height="100%",
        overflow="auto",
        **kwargs,
    )
