import reflex as rx

from supercog.dashboard.templates import slim_template
from supercog.dashboard.datums_state import DatumsState
from supercog.dashboard.state_models import UIDatum
from supercog.dashboard.templates.template import custom_page_dec
from supercog.dashboard.components.json_viewer import jsonviewer
from typing import List, Optional, Dict, Union

def datum_row(datum: UIDatum) -> rx.Component:
    return rx.chakra.tr(
        rx.chakra.td(
            rx.link(datum.name, on_click=DatumsState.load_datum(datum)),
        ),
        rx.chakra.td(
            rx.chakra.button(
                rx.chakra.icon(tag="delete"),
                on_click=DatumsState.delete_datum(datum),
                size="sm",
                variant="ghost",
            ),
        ),
    )

def datums_table(datums: list[UIDatum]) -> rx.Component:
    return rx.chakra.table_container(
        rx.chakra.table(
            rx.chakra.tbody(
                rx.foreach(datums, datum_row),
            ),
            class_name="files_table",
        ),
        width="280px",
    )

def adatum(datums: list[str, list[UIDatum]]) -> rx.Component:
    return rx.chakra.accordion(
        rx.chakra.accordion_item(
            rx.chakra.accordion_button(
                rx.chakra.heading(datums[0], size="sm"),
                rx.chakra.accordion_icon(),
            ),
            rx.chakra.accordion_panel(
                datums_table(datums[1]),
            ),
        ),
        allow_toggle=True,
        width="100%",
    )
def file_info_box() -> rx.Component:
    return rx.box(
        rx.markdown(DatumsState.file_info_markdown),
        padding="10px",
        border="1px solid #E2E8F0",
        border_radius="md",
        background_color="gray.50",
        margin_top="10px",
    )

'''
def file_info_box() -> rx.Component:
    return rx.box(
        rx.text("File Information:", font_weight="bold"),
        rx.text(f"Source:   {DatumsState.file_source}"),
        rx.cond(
            DatumsState.s3_url != "",
            rx.text(f"S3 URL:   {DatumsState.media_url}"),
            rx.text(f"Path:     {DatumsState.file_name_restricted}"),
        ),
        rx.text(f"Created:  {DatumsState.file_created}"),
        rx.text(f"Modified: {DatumsState.file_modified}"),
        rx.text(f"Size:     {DatumsState.file_size}"),
        padding="10px",
        border="1px solid #E2E8F0",
        border_radius="md",
        background_color="gray.50",
        margin_top="10px",
    )
'''

def debug_info_box() -> rx.Component:
    return rx.box(
        rx.cond(
            #DatumsState.datum_type in ["audio", "video", "image"],# not allowed in reflex
            rx.box(
                rx.text("Debug Information:", font_weight="bold"),
                rx.text(DatumsState.media_debug),
                rx.text("Image URL: " + DatumsState.image_url),
                rx.cond(
                    DatumsState.image_data_present,
                    rx.text("Image Data: Present"),
                    rx.text("Image Data: None")
                ),
                padding="10px",
                border="1px solid #E2E8F0",
                border_radius="md",
                background_color="gray.50",
                margin_top="10px",
                white_space="pre-wrap",
            ),
        ),
    )
def viewer_pane(left_margin: int = 0, top_margin: int = 0) -> rx.Component:
    return rx.chakra.box(
        rx.heading(DatumsState.datum_name, size="3", padding="4px"),
        rx.chakra.box(
            rx.cond(
                DatumsState.datum_type == "csv",
                rx.data_table(
                    data=DatumsState.table_data,
                    pagination={"limit":"20"},
                    search=True,
                    sort=True,
                    fixedHeader=True,
                    resizable=True,
                    style={"td": {"padding":"0"}},
                ),
            ),
            rx.cond(
                DatumsState.datum_type == "text",
                rx.markdown(
                    DatumsState.text_data,
                    style={"padding": "10px"},
                ),
            ),
            rx.cond(
                DatumsState.datum_type == "json",
                rx.chakra.accordion(
                    rx.chakra.accordion_item(
                        rx.chakra.accordion_button(
                            rx.chakra.text("details", size="sm"),
                            rx.chakra.accordion_icon(),
                        ),
                        rx.chakra.accordion_panel(
                            jsonviewer(data=DatumsState.json_data),
                        ),
                    ),
                    allow_toggle=True,
                    width="100%",
                ),
            ),
           rx.cond(
                DatumsState.datum_type == "image",
                rx.vstack(
                    rx.image(src=DatumsState.encoded_image),
                ),
            ),
            rx.cond(
                DatumsState.datum_type == "audio",
                rx.vstack(
                    rx.html(DatumsState.media_player),
                ),
            ),
            rx.cond(
                DatumsState.datum_type == "video",
                rx.vstack(
                    rx.html(DatumsState.media_player),
                ),
            ),
            rx.cond(
                DatumsState.datum_type == "email",
                rx.vstack(
                    rx.text("Email Content:"),
                    rx.text(f"Subject: {DatumsState.email_subject}"),
                    rx.text(f"From: {DatumsState.email_sender}"),
                    rx.text(f"To: {DatumsState.email_recipient}"),
                    rx.text(f"Date: {DatumsState.email_date}"),
                    rx.text("Body:"),
                    rx.cond(
                        DatumsState.is_html,
                        # Be cautious with user-generated content to avoid potential security
                        # issues like cross-site scripting (XSS) attacks.
                        rx.html(DatumsState.email_body),     # Use raw_html for HTML content
                        rx.markdown(DatumsState.email_body), # Use markdown for plain text
                    ),
                    spacing="4",
                ),
            ),
            file_info_box(),
            width=f"calc(100vw - {left_margin}px)",
            height=f"calc(100vh - {top_margin}px)",
            overflow="scroll",
        ),
        height="100%",
        flex="1",
        background_color="gray.100",
    )

def get_icon(item: Dict[str, Union[str, bool, int]]) -> rx.Component:
    return rx.cond(
        item["is_directory"],
        rx.cond(
            item["is_expanded"],
            rx.chakra.icon(tag="chevron_down"),
            rx.chakra.icon(tag="chevron_right"),
        ),
        rx.cond(
            item["datum_type"] == "csv",
            rx.icon("sheet", size=14),
            rx.cond(
                item["datum_type"] == "audio",
                rx.icon("audio-lines", size=14),
                rx.cond(
                    item["datum_type"] == "image",
                    rx.icon("image", size=14),
                    #rx.hstack(rx.text(item['mime_type']),rx.icon("file", size=10)),
                    rx.icon("file", size=14),
                ),
            ),
        ),
    )

def file_tree_item(item: Dict[str, Union[str, bool, int, str]]) -> rx.Component:
    return rx.box(
        rx.hstack(
            get_icon(item),
            rx.text(item["name"]),
            #rx.cond(
            #    item["is_directory"],
            #    rx.text(" (Dir)"),
            #    rx.text(" (File)")
            #),
            spacing="2",
            on_click=DatumsState.handle_item_click(item["path"]),
            cursor="pointer",
        ),
        padding_left=item["indentation"],
        width="100%",
        padding_y="1px",
    )

def file_browser() -> rx.Component:
    return rx.box(
        rx.button("Refresh", on_click=DatumsState.refresh),
        rx.heading("Files", size="3", margin_bottom="2"),
        rx.vstack(
            rx.foreach(
                DatumsState.flat_structure,
                file_tree_item
            ),
            align_items="stretch",
            width="100%",
            spacing="0",
        ),
        rx.text(f"Total items: {DatumsState.item_count}"),
        width="280px",
        height="calc(100vh - 90px)",
        border="1px solid #CCC",
        padding="4px",
        overflow="scroll",
    )


@slim_template(route="/datums/[appid]/[run_id]", title="Supercog: Datums", image="home", hide_nav=True,
                    on_load=DatumsState.on_mount)
def datums_page() -> rx.Component:
    return rx.hstack(
        file_browser(),
        viewer_pane(left_margin=290, top_margin=90),
        width="100%",
        height="100%",
        align_items="stretch",
    )

@slim_template(route="/datum/[appid]/[run_id]", title="Supercog: Data", image="home", hide_nav=True,
                    on_load=DatumsState.mount_single)
def single_datum_page() -> rx.Component:
    return rx.hstack(
        viewer_pane(left_margin=0, top_margin=60),
        width="100%",
        height="100%",
        align_items="stretch",
    )
