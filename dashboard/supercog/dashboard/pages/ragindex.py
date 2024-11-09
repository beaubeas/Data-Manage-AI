import reflex as rx
import functools

from supercog.dashboard.components.modal import BUTTON_STYLES
from supercog.dashboard.templates import template
from supercog.dashboard.ragindex_state import RAGIndexState

from supercog.dashboard.global_state  import require_google_login
from supercog.dashboard.components.chat import markdown_components
from supercog.dashboard.components.tool_icon import tool_icon
from supercog.dashboard.state_models import UIDocSource

## RAG Index page

def oauth_button(cred: UIDocSource) -> rx.Component:
    return rx.chakra.button(
        "Connect to " + cred.system_name, 
        on_click=RAGIndexState.oauth_authorize, 
        color_scheme="green", 
        size="lg"
    )

def cred_input(ktuple: tuple, auth_config: dict) -> rx.Component:
    return rx.chakra.hstack(
        rx.chakra.text(
            ktuple[2],
            width="200px"
        ),
        rx.cond(
            ktuple[1].to_string().contains(","),
            rx.chakra.select(
                ktuple[1].to(list),
                placeholder="Select an option",
                name=ktuple[0],
                on_change=lambda v: RAGIndexState.set_docsource_value(ktuple[0], v)
            ),
            rx.chakra.input(
                placeholder=auth_config[ktuple[0]], 
                name=ktuple[0],
                on_change=lambda v: RAGIndexState.set_docsource_value(ktuple[0],v)
            ),
        ),
        align_items="center",
        width="100%",
    )

def doc_source_header(cred: UIDocSource) -> rx.Component:
    return rx.hstack(
        rx.cond(
            cred.factory_id,
            tool_icon(
                tool_id=cred.factory_id,
                logo_url=cred.logo_url,
                tool_size=20
            ),
        ),
        rx.cond(
            RAGIndexState.is_editing_docsource,
            rx.text(f"Edit Source: {cred.system_name}"),
            rx.text(f"New Source: {cred.system_name}"),
        ),
        align="center",
        gap="1rem",
    )

def doc_source_modal(cred: UIDocSource) -> rx.Component:
    return rx.chakra.modal(
            rx.chakra.modal_overlay(
                rx.chakra.modal_content(
                    rx.chakra.modal_header(doc_source_header(cred)),
                    rx.chakra.modal_body(
                        rx.markdown(cred.help_msg, component_map=markdown_components, padding_bottom="10px", font_size="1.5em"),
                        rx.form(
                            rx.chakra.form_label("Document Source Name", html_for="cred_name"),
                            rx.chakra.input(
                                value=cred.name, 
                                on_change=lambda v: RAGIndexState.set_docsource_value("name",v),
                                id="cred_name_input",
                                margin_bottom="10px",
                            ),
                            rx.chakra.vstack(
                                rx.foreach(cred.config_list, 
                                    lambda pair: cred_input(pair, cred.auth_config)
                                ),
                                justify_content="stretch",
                            ),
                            rx.chakra.text(" ", padding_bottom="20px"),
                            id="cred_form",
                        ),
                        rx.cond(
                            cred.uses_oauth,
                            oauth_button(cred),
                        ),
                        rx.chakra.text(" ", padding_bottom="20px"),
                        width="100%",
                    ),
                    rx.chakra.modal_footer(
                        rx.hstack(
                            rx.chakra.hstack(
                                rx.chakra.button("Save", on_click=RAGIndexState.save_docsource),
                                rx.chakra.button("Cancel", on_click=RAGIndexState.toggle_doc_source_modal),
                            ),
                            justify="between",
                            width="100%",
                        ),
                    ),
                    min_width="600px",
                ),
        ),
        is_open=RAGIndexState.doc_source_modal_open,
        size="xl",
        on_close=RAGIndexState.toggle_doc_source_modal
    )

def doc_source_config_row(config: UIDocSource) -> rx.Component:
    return rx.table.row(
        rx.table.cell(config.name),
        rx.table.cell(config.provider_data),
        rx.table.cell(config.folder_ids),
        rx.table.cell(config.file_patterns),
        rx.table.cell(
            rx.chakra.button(
                rx.chakra.icon(tag="delete", size="sm"),
                on_click=RAGIndexState.delete_doc_source(config.id),
            )
        )
    )

def doc_sources_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell(
                    "Name",
                ),
                rx.table.column_header_cell(
                    "Provider info",
                ),
                rx.table.column_header_cell(
                    "Folders",
                ),
                rx.table.column_header_cell(
                    "File Patterns",
                ),
                rx.table.column_header_cell(""),
            ),
        ),
        rx.table.body(
            rx.foreach(
                RAGIndexState.doc_sources,
                doc_source_config_row,
            ),
        ),
        width="100%",
    )



def doc_row(doc: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(doc['name']),
        rx.table.cell(doc['show_id']),
        rx.table.cell(doc['status']),
        rx.table.cell(doc['chunk_count']),
        rx.table.cell(doc['created_at']),
        rx.table.cell(doc['owner']),
        #rx.table.cell(rx.checkbox()),
        rx.table.cell(
            rx.icon(tag="trash-2", size=15),
            on_click=lambda: RAGIndexState.delete_doc(doc['id']),
            variant="outline",
            size="sm"
        )
    )

def index_files_table() -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.button(
            rx.icon(tag="refresh-cw", size=15),
            on_click=RAGIndexState.bg_refresh,
            variant="outline",
            size="sm",
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell(
                        "Name",
                        padding_x="2px",
                        width="55%",
                    ),
                    rx.table.column_header_cell(
                        "Id",
                        padding_x="2px",
                        width="10%",
                    ),
                    rx.table.column_header_cell(
                        "Status",
                        padding_x="2px",
                        width="10%",
                    ),
                    rx.table.column_header_cell(
                        "Chunks",
                        padding_x="2px",
                        width="10%",
                    ),
                    rx.table.column_header_cell(
                        "Date",
                        padding_x="2px",
                        width="25%",
                    ),
                    rx.table.column_header_cell(
                        "Owner",
                        padding_x="2px",
                    ),
                    rx.table.column_header_cell(
                        "",
                        padding_x="2px",
                    ),
                )
            ),
            rx.table.body(
                rx.foreach(
                    RAGIndexState.index_files,
                    doc_row,
                ),
            ),
            width="100%",
        ),
        rx.chakra.hstack(
            rx.chakra.button(
                rx.icon(tag="chevron_left", size=15),
                on_click=RAGIndexState.bg_previous,
                variant="outline",
                size="sm",
            ),
            rx.chakra.button(
                rx.icon(tag="chevron_right", size=15),
                on_click=RAGIndexState.bg_next,
                variant="outline",
                size="sm",
            ),
            align_items="flex-end",
            width="100%",
        ),
        width="70%",
        align_items="flex-start",
    )


def upload_area() -> rx.Component:
    color = "rgb(107,99,246)"
    return rx.flex(
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
        width="300px",
        justify="center"
    )

def upload_button() -> rx.Component:
    return rx.button(
        "Upload",
        on_click=RAGIndexState.handle_upload(
            rx.upload_files(
                upload_id="upload1", 
            ),
        ),
        align_items="center",
        disabled=RAGIndexState.file_uploading,
    )

def search_panel() -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.heading("Quick index search", size="md"),
        rx.chakra.form(
            rx.chakra.input(
                placeholder="Doc Search...",
                name="search",
                width="100%",
            ),
            rx.chakra.button(
                "Search",
                variant="outline",
                size="sm",
                type_="submit",
            ),
            on_submit=RAGIndexState.index_search,
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell(
                        "Match",
                        padding_x="2px",
                        width="60%",
                    ),
                    rx.table.column_header_cell(
                        "Doc",
                        padding_x="2px",
                        width="15%",
                    ),
                    rx.table.column_header_cell(
                        "Type",
                        padding_x="2px",
                        width="15%",
                    ),
                    rx.table.column_header_cell(
                        "Score",
                        padding_x="2px",
                        width="10%",
                    ),
                )
            ),
            rx.table.body(
                rx.foreach(
                    RAGIndexState.index_search_results,
                    lambda doc: rx.table.row(
                        rx.table.cell(doc['text']),
                        rx.table.cell(doc['document_name']),
                        rx.table.cell(doc['type']),
                        rx.table.cell(doc['score']),
                    )
                ),
            ),
            width="100%",
        ),
        width="100%",
        align_items="flex-start",
        margin_bottom="10em !important",
    )

@template(route="/sconnections/index/[index_id]", title="Supercog: RAG Index", 
          image="cable", hide_nav=True, on_load=RAGIndexState.rag_index_page_load)
@require_google_login
def rag_index_page() -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.breadcrumb(
            rx.chakra.breadcrumb_item(
                rx.chakra.breadcrumb_link("Connections", href=f"/sconnections"),
                color="blue.500",
            ),
            rx.chakra.breadcrumb_item(
                rx.chakra.breadcrumb_link(
                    RAGIndexState.doc_index['name'],
                    is_current_page=True,
                    style={
                        "cursor": "default !important",
                        "textDecoration": "none",
                    }
                )
            ),            
        ),
        rx.chakra.hstack(
            rx.chakra.vstack(
                rx.chakra.heading("RAG Index", font_size="lg", flex="1"),
                rx.chakra.text("Index Name"),
                rx.chakra.input(
                    value=RAGIndexState.doc_index['name'],
                    on_change=RAGIndexState.update_index_name,
                ),
                rx.chakra.text("Describe the source or contents of this Knowledge Base"),
                rx.chakra.hstack(
                    rx.chakra.input(
                        value=RAGIndexState.doc_index['source_description'],
                        on_change=RAGIndexState.update_source_description,
                    ),
                    rx.chakra.vstack(
                        rx.chakra.text("Shared"),
                        rx.chakra.switch(
                            is_checked=RAGIndexState.doc_index['scope'] == 'shared', 
                            on_change=RAGIndexState.toggle_is_shared,
                        ),
                    ),
                    width="100%",
                ),
                rx.chakra.heading("Document Sources", size="md"),
                rx.chakra.select(
                    rx.foreach(RAGIndexState.avail_doc_sources, 
                                    lambda tool: rx.chakra.option(tool["system_name"], 
                                                        value=tool["id"]),
                    ),
                    on_change=RAGIndexState.select_doc_factory,
                ),
                rx.chakra.button(
                    "Add Document Source",
                    on_click=RAGIndexState.add_doc_source,
                    variant="outline",
                    color_scheme="blue",
                    size="sm",
                ),
                doc_sources_table(),
                width="70%",
                align_items="flex-start",
            ),
            upload_area(),
            width="100%",
        ),
        rx.chakra.heading("Docs in Index", size="md"),
        index_files_table(),
        search_panel(),
        doc_source_modal(RAGIndexState.doc_source),
        align_items="flex-start",
        class_name="vspacing",
    )
