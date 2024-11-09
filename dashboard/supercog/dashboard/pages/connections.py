"""The dashboard page."""
import reflex as rx
import functools

from supercog.dashboard.components.modal import BUTTON_STYLES
from supercog.dashboard.templates import template
from supercog.dashboard.state_models import LocalCred
from supercog.dashboard.connections_state import ConnectionsState
from supercog.dashboard.components.tool_icon import tool_icon
from supercog.shared.services import get_public_service_host

from supercog.dashboard.global_state  import require_google_login
from supercog.dashboard.components.chat import markdown_components

# This is the new tool credentials page. 

# It is really managing Credential records, both private and shared.
# When you want to connect a new system you select the system
# name from the list of ToolFactories, and we show you a panel
# to configure that type of tool.

def confirm_delete_credential() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.text("Are you sure you want to remove this connection?")
                ),
                rx.chakra.modal_body(
                    rx.chakra.box()
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Yes",
                            style=BUTTON_STYLES,
                            on_click=ConnectionsState.delete_item('credential'),
                        ),
                        rx.chakra.button(
                            "No",
                            style=BUTTON_STYLES,
                            on_click=ConnectionsState.toggle_delete_modal('credential', ''),
                        ),
                        align_items="space-between",
                    ),
                ),
                bg="#222",
                color="#fff",
            ),
        ),
        is_open=ConnectionsState.open_modals['credential'],
    )

def confirm_delete_index_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header(
                    rx.chakra.text("Are you sure you want to delete this index?")
                ),
                rx.chakra.modal_body(
                    rx.chakra.box()
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Yes",
                            style=BUTTON_STYLES,
                            on_click=ConnectionsState.delete_item('docindex'),
                        ),
                        rx.chakra.button(
                            "No",
                            style=BUTTON_STYLES,
                            on_click=ConnectionsState.toggle_delete_modal('docindex', ''),
                        ),
                        align_items="space-between",
                    ),
                ),
                bg="#222",
                color="#fff",
            ),
        ),
        is_open=ConnectionsState.open_modals['docindex'],
    )


def credrows(cred: LocalCred) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.cond(
                cred.factory_id,
                tool_icon(
                    tool_id=cred.factory_id,
                    logo_url=cred.logo_url,
                    tool_size=20
                ),
            )
        ),
        rx.table.cell(
            rx.chakra.link(
                cred.name,
                on_click=ConnectionsState.edit_credential(cred.id),
            ),
        ),
        rx.table.cell(cred.system_name),
        rx.table.cell(cred.owner),
        rx.table.cell(rx.chakra.checkbox(is_checked=cred.is_shared, is_disabled=True)),
        rx.cond(
            cred.owner_id == ConnectionsState.user_id,
            rx.table.cell(
                rx.hstack(
                    rx.chakra.button("Edit",
                        on_click=functools.partial(ConnectionsState.edit_credential, cred.id)),
                    rx.chakra.button(
                        rx.chakra.icon(tag="delete", size="sm"), 
                        on_click=ConnectionsState.toggle_delete_modal('credential', f"credential:{cred.id}"),
                    ),
                    gap="1rem",
                )
            ),
        ),
        bg=rx.cond(ConnectionsState.selected_cred_name == cred.name, "#FFFFE0", ""),
        align="center",
    )

def cred_table_category_header(cred: LocalCred) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.chakra.hstack(
                tool_icon(
                    tool_id=cred.factory_id,
                    logo_url=cred.logo_url,
                    tool_size=24
                ),
                rx.chakra.link(
                    rx.fragment(
                        # Arrow Icon Logic
                        rx.cond(
                            ConnectionsState.expanded_systems.contains(
                                cred.system_name
                            ),
                            "▼ ",
                            "▶ ",
                        ),
                        cred.system_name,
                    ),
                    on_click=lambda: ConnectionsState.toggle_system_group(cred.system_name),
                    class_name="cred_cateory_link",
                ),
                spacing="10px"  # Optional: Adjust spacing between elements
            ),
        ),
        # Empty columns so borders expand
        rx.table.cell(),
        rx.table.cell(),
        rx.table.cell(),
        rx.table.cell(),
        rx.table.cell(),
        align="center",
    )

def connections_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell(
                    "",
                    padding_x="2px",
                    width="25%",
                ),
                rx.table.column_header_cell(
                    "Name",
                    padding_x="2px",
                    width="15%",
                ),
                rx.table.column_header_cell(
                    "Tool",
                    padding_x="2px",
                    width="15%",
                ),
                rx.table.column_header_cell(
                    "Owner",
                    padding_x="2px",
                    width="15%",
                ),
                rx.table.column_header_cell(
                    "Shared",
                    padding_x="2px",
                    width="10%",
                ),
                rx.table.column_header_cell(
                    "Actions",
                    padding_x="2px",
                    width="20%",
                ),
            )
        ),
        rx.table.body(
            rx.foreach(
                ConnectionsState.all_credentials,  # Use all_credentials
                lambda cred: rx.fragment(
                    rx.cond(
                        cred.is_category_header,
                        cred_table_category_header(cred),
                        rx.cond(
                            ConnectionsState.expanded_systems.contains(
                                cred.system_name
                            ),
                            credrows(cred),
                        ),
                    )
                ),
            ),
        ),
        width="100%",
    )

def doc_sources_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell(
                    "",
                    padding_x="2px",
                    width="25%",
                ),
                rx.table.column_header_cell(
                    "Name",
                    padding_x="2px",
                    width="15%",
                ),
                rx.table.column_header_cell(
                    "Tool",
                    padding_x="2px",
                    width="15%",
                ),
                rx.table.column_header_cell(
                    "Owner",
                    padding_x="2px",
                    width="15%",
                ),
                rx.table.column_header_cell(
                    "Shared",
                    padding_x="2px",
                    width="10%",
                ),
                rx.table.column_header_cell(
                    "Actions",
                    padding_x="2px",
                    width="20%",
                ),
            )
        ),
        rx.table.body(
            rx.foreach(
                ConnectionsState.doc_sources,
                credrows,
            ),
        ),
        width="100%",
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
                on_change=lambda v: ConnectionsState.save_cred_value(ktuple[0], v)
            ),
            rx.chakra.input(
                placeholder=auth_config[ktuple[0]], 
                name=ktuple[0],
                on_change=lambda v: ConnectionsState.save_cred_value(ktuple[0],v)
            ),
        ),
        align_items="center",
        width="100%",
    )

def oauth_button(cred: LocalCred) -> rx.Component:
    return rx.chakra.form(
        rx.chakra.input(value=ConnectionsState.get_ut_id, name="ut_id", on_change=ConnectionsState.ignore_change, type_="hidden"), 
        rx.chakra.input(value=cred.factory_id, name="tool_factory_id", on_change=ConnectionsState.ignore_change, type_="hidden"),
        rx.chakra.input(name="cred_name", type_="hidden"),
        rx.chakra.input(value=ConnectionsState.get_server_host, name="return_url", on_change=ConnectionsState.ignore_change, type_="hidden"),
        rx.chakra.button("Connect to " + cred.system_name, type_="submit", color_scheme="green", size="lg"),
        id="oauth_form",
    )

ENGINE_SERVICE_HOST = get_public_service_host("engine")

def cred_header(cred: LocalCred) -> rx.Component:
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
            ConnectionsState.is_editing_connection,
            rx.text(f"Edit Connection: {cred.system_name}"),
            rx.text(f"New Connection: {cred.system_name}"),
        ),
        align="center",
        gap="1rem",
    )

def connection_modal(cred: LocalCred) -> rx.Component:
    return rx.chakra.modal(
            rx.chakra.modal_overlay(
                rx.chakra.modal_content(
                    rx.chakra.modal_header(cred_header(cred)),
                    rx.chakra.modal_body(
                        rx.markdown(
                            f"<i>{cred.tool_help}</i>", 
                            component_map=markdown_components,
                            font_size="1.5em"
                        ),
                        rx.markdown(cred.help_msg, component_map=markdown_components, padding_bottom="10px", font_size="1.5em"),
                        rx.form(
                            rx.chakra.form_label("Connection Name", html_for="cred_name"),
                            rx.chakra.input(
                                value=cred.name, 
                                on_change=lambda v: ConnectionsState.save_cred_value("name",v),
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
                        rx.chakra.text("Shared Connection", font_style="bold", font_size="1.5em"),
                        rx.chakra.switch(
                            is_checked=cred.is_shared, 
                            on_change=ConnectionsState.change_is_shared,
                        ),
                        width="100%",
                    ),
                    rx.cond(
                        ConnectionsState.is_loading,
                        rx.chakra.spinner(size="sm", margin_left="20px")
                    ),
                    rx.chakra.text(ConnectionsState.test_credentials_status_message, padding_left="20px"),
                    rx.chakra.modal_footer(
                        rx.hstack(
                            rx.chakra.button(
                                "Test Connection",
                                on_click=ConnectionsState.test_connection,
                                color_scheme="blue"
                            ),
                            rx.chakra.hstack(
                                rx.chakra.button("Save", on_click=ConnectionsState.save_credential),
                                rx.chakra.button("Cancel", on_click=ConnectionsState.cancel_credential),
                            ),
                            justify="between",
                            width="100%",
                        ),
                    ),
                    min_width="600px",
                ),
        ),
        rx.script(f"""
                  setTimeout(function() {{
                    window.setup_oauth_form('{ENGINE_SERVICE_HOST}');
                  }}, 100)
        """),
        is_open=ConnectionsState.connections_modal_open,
        size="xl",
        on_close=ConnectionsState.on_modal_close
    )

def connections_section() -> list[rx.Component]:
    return [rx.chakra.hstack(
            rx.chakra.heading("Connections", font_size="lg"),
            rx.chakra.spacer(),
            rx.chakra.button(
                rx.icon(tag="refresh-cw", size=15),
                variant="outline",
                on_click=lambda: ConnectionsState.load_connections(True)
            ),
        ),
        rx.chakra.hstack(
            rx.chakra.select(rx.foreach(ConnectionsState.avail_tools, 
                                lambda tool: rx.chakra.option(tool["system_name"], 
                                                       value=tool["id"]),
                    ),
                on_change=ConnectionsState.select_factory,
            ),
            rx.chakra.spacer(), 
            rx.chakra.button(
                "New Connection", 
                width="200px",
                color_scheme="blue",
                on_click=ConnectionsState.new_credential
            ),
        ),
        connections_table(),
    ]

def indexes_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell(
                    "Name",
                    padding_x="2px",
                ),
                rx.table.column_header_cell(
                    "Owner",
                    padding_x="2px",
                ),
                rx.table.column_header_cell(
                    "Shared",
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
                ConnectionsState.doc_indexes,
                lambda index: rx.table.row(
                    rx.table.cell(
                        rx.chakra.link(
                            index.name,
                            href="/sconnections/index/" + index.id,
                        ),
                    ),
                    rx.table.cell(index.owner),
                    rx.table.cell(rx.chakra.checkbox(is_checked=index.is_shared, is_disabled=True)),
                    rx.table.cell(
                        rx.chakra.button(
                            rx.chakra.icon(tag="delete", size="sm"),
                            on_click=ConnectionsState.toggle_delete_modal('docindex', f"docindex:{index.id}"),
                        )
                    ),
                ),
            ),
        ),
        width="100%",
    )

def indexes_section() -> list[rx.Component]:
    return [
        # Document sources
        rx.chakra.hstack(
            rx.chakra.heading("Knowledge Indexes (RAG)", font_size="lg", margin_top="40px !important"),
        ),
        rx.chakra.button(
            "New Index", 
            color_scheme="blue",
            on_click=ConnectionsState.new_index,
        ),
        indexes_table(),
        rx.vstack(
            rx.chakra.spacer(),
            min_height="40px",
        ),
    ]

@template(route="/sconnections", title="Supercog: Connections", 
          image="cable", on_load=ConnectionsState.connections_page_load)
@require_google_login
def connections_page() -> rx.Component:
    return rx.chakra.vstack(
        *connections_section(),
        *indexes_section(),
        confirm_delete_credential(),
        confirm_delete_index_modal(),
        connection_modal(ConnectionsState.new_cred),
        rx.script(src="/custom.js"), 
        align_items="flex-start",
    )

