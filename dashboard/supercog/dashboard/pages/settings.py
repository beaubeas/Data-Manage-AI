import reflex as rx

from supercog.dashboard.global_state  import require_google_login
from supercog.dashboard.components.usage_tables import usage_tables
from supercog.dashboard.components.accordion_item import accordion_item

from supercog.dashboard.templates import template
from supercog.dashboard.global_state import GlobalState
from supercog.dashboard.settings_state import SettingsState

def username_input() -> rx.Component:
    return rx.cond(
        GlobalState.is_authenticated,
        rx.chakra.input(
            type="text",
            value=GlobalState.authenticated_user.name,
            on_change=SettingsState.set_username,
            margin_bottom="2em !important",
        ),
    )

def secret_row(secret: tuple, index: int) -> rx.Component:
    return rx.chakra.tr(
        rx.chakra.td(
            rx.chakra.input(
                value=secret[0],
                on_change=lambda v: SettingsState.save_secret_key(v, index)
            ),
        ),
        rx.chakra.td(
            rx.chakra.input(
                value=secret[1],
                on_change=lambda v: SettingsState.save_secret_value(v, index)
            ),
        ),
        rx.chakra.td(
            rx.chakra.button(
                rx.chakra.icon(tag="delete"), 
                on_click=SettingsState.delete_secret(index),
            ),
        ),
    )

def user_secrets_table() -> rx.Component:
    return accordion_item(
        header=rx.fragment(
            rx.chakra.heading("Env Vars", size="sm"),
            rx.chakra.accordion_icon(),
        ),
        content=rx.vstack(
            rx.chakra.table(
                rx.chakra.thead(
                    rx.chakra.tr(
                        rx.chakra.th("Name"),
                        rx.chakra.th("Value"),
                        rx.chakra.th(""),
                    )
                ),
                rx.chakra.tbody(
                    rx.foreach(SettingsState.user_secrets, secret_row)
                ),
            ),
            rx.chakra.hstack(
                rx.chakra.button(
                    "New",
                    on_click=SettingsState.add_secret
                ),
                rx.chakra.hstack(
                    rx.chakra.text("Add Special:"),
                    rx.chakra.select(
                        ["", "OPENAI_API_KEY", "CLAUDE_API_KEY", "GROQ_API_KEY", "EMAIL_WHITELIST"],
                        on_change=SettingsState.add_special_secret,
                    ),
                    width="260px",
                ),
                rx.chakra.spacer(),
                rx.chakra.button(
                    "Save",
                    color_scheme="green",
                    is_disabled=rx.cond(SettingsState.secrets_changed, False, True),
                    on_click=SettingsState.save_secrets,
                    size="sm",
                    variant="solid",
                ),
                width="100%",
            ),
            width="100%",
        )
    )

def org_selector() -> rx.Component:
    return rx.chakra.box(
        rx.chakra.select(
            SettingsState.avail_tenants,
            value=SettingsState.selected_tenant,
            on_change=SettingsState.select_tenant,
        ),
        margin_bottom="3em !important",
    )

def member_row(member: dict[str,str]) -> rx.Component:
    return rx.chakra.tr(
        rx.chakra.td(member["email"]),
        rx.chakra.td(
            rx.cond(
                (SettingsState.is_admin & (member["user_id"] != GlobalState.user_id) & (member["role"] != "owner")),
                rx.select(
                    ["admin", "member"],
                    value=member["role"],
                    on_change=lambda value: SettingsState.update_member_role(member["user_id"], value),
                ),
                rx.text(member["role"]),
            )
        ),
        rx.chakra.td(
            rx.cond(
                SettingsState.is_admin,
                rx.cond(
                    member["user_id"] != GlobalState.user_id,
                    rx.chakra.button(
                        rx.chakra.icon(tag="delete"), 
                        on_click=SettingsState.delete_org_member(member["user_id"]),
                    ),
                ),
            )
        ),
    )

def org_members() -> rx.Component:
    return accordion_item(
        header=rx.fragment(
            rx.chakra.heading("Organization Members", size="sm"),
            rx.chakra.hstack(
                rx.cond(
                    SettingsState.is_admin,
                    rx.chakra.button(
                        "Add Member", 
                        on_click=SettingsState.toggle_add_member_model.stop_propagation,
                        color_scheme="green",
                        size="sm",
                        align_self="flex-end",
                    ),
                ),
                rx.chakra.accordion_icon(),
                gap="0.5rem",
            ),
        ),
        content=rx.chakra.vstack(
            rx.chakra.table(
                rx.chakra.thead(
                    rx.chakra.tr(
                        rx.chakra.th("Email"),
                        rx.chakra.th("Role"),
                        rx.chakra.th(""),
                    )
                ),
                rx.chakra.tbody(
                    rx.foreach(
                        SettingsState.tenant_members, 
                        member_row
                    ),
                ),
            ),
        ),
    )

def org_name() -> rx.Component:
    return accordion_item(
        header=rx.fragment(
            rx.chakra.heading("Organization Name", size="sm"),
            rx.chakra.accordion_icon(),
        ),
        content=rx.chakra.input(
            type="text",
            value=SettingsState.tenant_name,
            on_change=SettingsState.update_tenant_name,
            is_disabled=~SettingsState.is_admin,
            margin_bottom="2em !important",
        ),
    )
    

def add_member_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header("Add Member"),
                rx.chakra.modal_body(
                    rx.chakra.vstack(
                        rx.chakra.heading("Add a member to your organization", size="sm"),
                        rx.chakra.text("Email"),
                        rx.chakra.input(
                            type="text",
                            on_change=SettingsState.set_new_member_email,
                        ),
                        rx.chakra.text("Role"),
                        rx.chakra.select(
                            ["member", "admin"],
                            on_change=SettingsState.set_new_member_role,
                        ),
                        align_items="flex-start",
                    ),
                ),
                rx.chakra.modal_footer(
                    rx.chakra.button(
                        "Cancel",
                        on_click=SettingsState.toggle_add_member_model,
                    ),
                    rx.chakra.button(
                        "Save",
                        color_scheme="blue",
                        on_click=SettingsState.add_org_member
                    ),
                    justify_content="space-between", 
                ),
                background="white",
                color="black",
                min_width="420px",
            ),
        ),
        is_open=SettingsState.add_member_modal_open,
        size="md",
    )

def usage_collapsible() -> rx.Component:
    return accordion_item(
        header=rx.fragment(
            rx.chakra.heading("Usage", size="sm"),
            rx.chakra.accordion_icon(),
        ),
        content=usage_tables(),
    )


@template(route="/settings", title="Supercog: Settings", image="settings", on_load=SettingsState.settings_page_load)
@require_google_login
def settings_page() -> rx.Component:
    """The Settings page.
    """

    return rx.chakra.vstack(
        rx.chakra.heading("Settings"),
        rx.cond(
            GlobalState.is_hydrated & GlobalState.user_is_admin,
            rx.chakra.link(
                rx.chakra.button("Admin Info", size="sm"),
                href="/admin",
            ),
        ),
        rx.chakra.text("Select Active Organization", as_="i"),
        org_selector(),
        rx.chakra.hstack(
            rx.chakra.vstack(
                rx.chakra.heading("User name", size="sm"),
                username_input(),
                flex_grow="1",
            ),
            rx.chakra.vstack(
                rx.chakra.heading("Email", size="sm"),
                rx.chakra.text(GlobalState.authenticated_user.email),
                flex_grow="1",
            ),
            width="100%",
            align_items="flex-start",
        ),
        rx.chakra.accordion(
            org_name(),
            org_members(),
            user_secrets_table(),
            usage_collapsible(),
            allow_toggle=True,
            allow_multiple=True,
            default_index=[0, 1, 2],
            width="100%",
            margin_top="2rem !important",
        ),
        add_member_modal(),
        max_w="60vw",
        padding_bottom="40px",
        overflow="scroll",
        align_items="flex-start",
    )
    

