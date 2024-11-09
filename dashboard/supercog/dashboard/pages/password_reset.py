from sqlmodel import select

import reflex as rx

from supercog.dashboard.login_state import LoginState
from supercog.dashboard.templates.template import custom_page_dec

def send_email_card() -> rx.Component:
    return rx.chakra.card(
        rx.chakra.form(
            rx.chakra.vstack(
                rx.chakra.input(
                    placeholder="email address", 
                    value=LoginState.pwreset_email, 
                    on_change=LoginState.set_pwreset_email
                ),
                rx.chakra.button("Send reset link", color_scheme="blue", on_click=LoginState.send_pwreset),
                rx.chakra.text(LoginState.pwreset_message, color="blue", padding_top="10px"),
                align_items="center",
                width="100%",
            ),
        ),
        header=rx.chakra.heading("Enter your email to reset your password", size="md", padding_bottom="20px"),
    )

def reset_password_card() -> rx.Component:
    return rx.chakra.card(
        rx.chakra.form(
            rx.chakra.vstack(
                rx.chakra.password(
                    placeholder="password", 
                    name="password",
                ),
                rx.chakra.password(
                    placeholder="confirm password", 
                    name="confirm_password",
                ),
                rx.chakra.button("Reset password", color_scheme="blue", type_="submit"),
                rx.chakra.text(LoginState.pwreset_message, color="blue", padding_top="10px"),
                align_items="center",
                width="100%",
            ),
            on_submit=LoginState.reset_password,
        ),
        header=rx.chakra.heading("Enter your new password", size="md", padding_bottom="20px"),
    )
 
@custom_page_dec(route="/pwreset", title="Reset password", image="home", hide_nav=True,
         on_load=LoginState.pwreset_page_load)
def pwreset_page() -> rx.Component:
    return rx.vstack(
        rx.cond(
            LoginState.pwreset_secret,
            reset_password_card(),
            send_email_card(),
        ),
        align_items="center",
        width="100%",
    )
