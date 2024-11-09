import reflex as rx

from supercog.dashboard.global_state import LOGO
from supercog.dashboard.login_state import LoginState, GOOGLE_CLIENT_ID
from supercog.dashboard.global_state import REGISTER_ROUTE
from supercog.dashboard.templates.template import custom_page_dec

from supercog.dashboard.auth.google_login import get_google_login_button

def email_login_page() -> rx.Component:
    """Render the login page.

    Returns:
        A reflex component.
    """
    login_form = rx.chakra.form(
        rx.chakra.vstack(
            rx.chakra.input(placeholder="Email", id="email"),
            rx.chakra.vstack(
                rx.chakra.password(placeholder="Password", id="password"),
                rx.chakra.box(
                    rx.chakra.link("Reset my password",
                        href="/pwreset",
                    ),
                ),
                align_items="flex-end",
                width="100%",
            ),
            rx.chakra.button(
                "Log In", 
                type_="submit", 
                color_scheme="linkedin",
                width="100%"
            ),
            gap="1rem",
            width="100%",
        ),
        on_submit=LoginState.on_submit_email_login,
        width="400px",
    )

    return rx.fragment(
        rx.chakra.vstack(
            rx.cond(  # conditionally show error messages
                LoginState.reg_error_message != "",
                rx.chakra.text(LoginState.reg_error_message, color="red"),
            ),
            login_form,
            rx.hstack(
                rx.chakra.text("Need an account?"),
                rx.chakra.link("Create an account",
                    href=f"{REGISTER_ROUTE}{LoginState.get_query_params}",
                    font_weight="bold",
                    padding_bottom="20px",
                ),
            ),
        ),
    )

@custom_page_dec(route="/", title="Supercog: Login", image="home", hide_nav=True, on_load=LoginState.on_page_load)
def login_page() -> rx.Component:
    return rx.chakra.vstack(
        rx.cond(
            LoginState.is_authenticated,
            rx.box(
                rx.chakra.button(
                    "Go to Dashboard", 
                    color_scheme="linkedin",
                    on_click=LoginState.redir(),
                ),
                padding="20px",
            ),
            rx.chakra.text(" ", padding_bottom="60px"),
        ),
        rx.chakra.card(
            rx.chakra.vstack(
                rx.chakra.vstack(
                    rx.chakra.heading(
                        "Log in to your account", 
                        size="md", 
                        padding_bottom="10px", 
                    ),
                    get_google_login_button(
                        client_id=GOOGLE_CLIENT_ID, 
                        on_success=LoginState.on_google_auth,
                    ),
                    rx.box(min_height="1em"),
                    rx.hstack(
                        rx.divider(orientation="horizontal"),
                        rx.chakra.text("or"),
                        rx.divider(orientation="horizontal"),
                        width="100%",
                        align_items="center",
                    ),
                    class_name=rx.cond(
                        bool(GOOGLE_CLIENT_ID) & (GOOGLE_CLIENT_ID != "skip"),
                        "",
                        "hide-google-login",
                    ),
                    width="100%",
                ),
                email_login_page(),
            ),
            header=rx.chakra.image(
                src=LOGO,
                height="8em",
            ),
            padding="50px",
            width="500px",
            border="1px solid #DEDEDE",
            align_items="center",
        ),
        align_items="center",
    )
