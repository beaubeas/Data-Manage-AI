import functools
import reflex as rx

from supercog.dashboard.global_state  import require_google_login
from supercog.dashboard.templates import template
from supercog.dashboard.filespage_state import FilespageState

def file_row(file: dict) -> rx.Component:
    return rx.chakra.tr(
        rx.chakra.td(
            rx.chakra.checkbox(
                on_change=FilespageState.toggle_file_selection(file['name']),
                is_checked=FilespageState.is_file_selected[file['name']],
            ),
            padding="0",
            width="1%",
            vertical_align="middle",
        ),
        rx.chakra.td(
            rx.link(
                file['name'],
                on_click=FilespageState.download_s3_file(file['name']),
                class_name="file_link",
            ),
        ),
        rx.chakra.td(
            rx.moment(
                file['last_modified'],
                from_now=True
            )
        ),
        rx.chakra.td(file['size']),
        rx.chakra.td(
            rx.chakra.button(
                rx.icon(tag="trash-2", size=15),
                on_click=FilespageState.delete_file(file['name']),
                variant="outline",
                size="sm",
            ),
        ),
    )


def files_table() -> rx.Component:
    return rx.chakra.table(
        rx.chakra.thead(
            rx.chakra.tr(
                rx.chakra.th(
                    rx.chakra.checkbox(
                        is_checked=FilespageState.all_files_selected,
                        on_change=FilespageState.select_all_files,
                    ),
                    padding="1",
                    width="1%",
                    vertical_align="middle",
                ),
                rx.chakra.th("Name"),
                rx.chakra.th("Date"),
                rx.chakra.th("Size"),
                rx.chakra.th("Delete"),
            )
        ),
        rx.chakra.tbody(
            rx.foreach(FilespageState.files, file_row)
        ),
        size="sm",
    )

def upload_button() -> rx.Component:
    return rx.button(
        "Upload",
        on_click=FilespageState.handle_upload(
            rx.upload_files(
                upload_id="upload1", 
            ),
        ),
        align_items="center",
        disabled=FilespageState.file_uploading,
    )

@template(route="/mfiles", title="Supercog: Files", image="file",
          on_load=FilespageState.files_page_load, hide_nav=False)
@require_google_login
def files_page() -> rx.Component:
    """The files page.
    """
    color = "rgb(107,99,246)"

    return rx.vstack(
        rx.box(
            rx.foreach(
                FilespageState.debug_info.split("\n"),
                lambda line: rx.text(line)
            ),
            white_space="pre-wrap",
        ),
        #rx.text(FilespageState.debug_info),
        rx.cond(
            FilespageState.files_status != "",
            rx.callout(
                FilespageState.files_status,
                icon="info",
                width="100%",
                padding="4px",
            ),
            rx.box(
                min_height="20px",
                width="100%",
                id="spacer_box",
            ),
        ),
        rx.flex(
            rx.box(
                rx.vstack(
                    rx.upload(
                        rx.box(
                            rx.vstack(
                                rx.upload(
                                    rx.button("Select File", color=color, bg="white", border=f"1px solid {color}"),
                                    id="upload1",
                                    spacing="1em",
                                ),
                                rx.text("Drag and drop files here or click to select files"),
                                rx.vstack(
                                    rx.foreach(
                                        rx.selected_files("upload1"),
                                        lambda file: rx.text(
                                            file,
                                            max_width="100%",
                                            overflow="hidden",
                                            text_overflow="ellipsis",
                                            white_space="nowrap",
                                        )
                                    ),
                                    width="100%",
                                    align_items="center",
                                ),
                                width="100%",
                                spacing="1em",
                                align_items="center",
                            ),
                            padding="1em",
                            border=f"1px dotted {color}",
                            align_items="center",
                            width="100%",
                            justify="between",
                        ),
                        id="upload1",
                        width="100%",
                        no_click=True,
                    ),
                    upload_button(),
                    align_items="center",
                    width="100%",
                    justify="between",
                ),
                class_name="w-full sm:w-3/5",
            ),
            width="100%",
            justify="center"
        ),
        rx.hstack(
            rx.chakra.heading("Files", size="md", font_size="1.5em"),
            rx.chakra.button(
                rx.icon(tag="refresh-cw", size=15),
                on_click=FilespageState.files_page_load,
                variant="outline",
                size="sm",
            ),
            rx.chakra.button(
                rx.icon(tag="trash-2", size=15),
                on_click=FilespageState.delete_selected_files,
                variant="outline",
                size="sm",
                is_disabled=FilespageState.selected_files.length() == 0,
            ),
            rx.chakra.spacer(),
            width="100%",
            justify="between",
        ),
        rx.box(
            files_table(),
            overflow_y="scroll",
            width="100%",
        ),
        padding="2em",
        width="100%",
        height="100%",
    )
