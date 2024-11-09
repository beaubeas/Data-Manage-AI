from sqlmodel import select

import reflex as rx

from supercog.dashboard.global_state import LOGO, REGISTER_ROUTE
from supercog.dashboard.login_state import LoginState, GOOGLE_CLIENT_ID
from supercog.dashboard.templates.template import custom_page_dec
from supercog.dashboard.auth.google_login import get_google_login_button

def email_register_form() -> rx.Component:
    register_form = rx.chakra.form(
            rx.chakra.vstack(
                rx.chakra.input(placeholder="Email", id="email"),
                rx.chakra.input(placeholder="Name", id="name"),
                rx.chakra.password(placeholder="Password", id="password"),
                rx.chakra.password(placeholder="Confirm password", id="confirm_password"),
                rx.chakra.button(
                    "Register",
                    type_="submit",
                    color_scheme="linkedin",
                    width="100%",
                    margin_top="2rem !important",
                ),
                gap="1rem",
                width="100%",
            ),
            on_submit=LoginState.handle_registration,
            width="400px",
        )
    return rx.fragment(
        rx.cond(
            LoginState.reg_success,
            rx.chakra.vstack(
                rx.chakra.text("Registration successful!"),
                rx.chakra.heading("Please check your email to verify your account.", size="md"),
                rx.chakra.link("Return to login", href="/"),
            ),
            rx.chakra.vstack(
                rx.cond(  # conditionally show error messages
                    LoginState.reg_error_message != "",
                    rx.callout(
                        LoginState.reg_error_message, 
                        color_scheme="red",
                    ),
                ),
                register_form,
            ),
        )
    )            
    
# /register
@custom_page_dec(route=REGISTER_ROUTE, title="Create an Account", image="home", hide_nav=True, on_load=LoginState.register_page_load)
def register_page() -> rx.Component:
    return rx.vstack(
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
                    get_google_login_button(
                        client_id=GOOGLE_CLIENT_ID, 
                        on_success=LoginState.on_google_auth,
                    ),
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
                    width="100%"
                ),
                email_register_form(),
            ),
            header=rx.chakra.link(
                rx.chakra.image(
                    src=LOGO,
                    height="8em",
                ),
                href="/",
            ),
            padding="50px",
            width="600px",
            border="1px solid #DEDEDE",
            align_items="center",
        ),
        align_items="center",
        width="100%",
    )
