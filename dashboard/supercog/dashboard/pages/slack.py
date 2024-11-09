import reflex as rx

from supercog.dashboard.global_state import LOGO
from supercog.dashboard.slack_state import SlackState
from supercog.dashboard.templates.template import custom_page_dec

from supercog.dashboard.components.slack_buttons import slack_install_button, slack_deep_link_button

@custom_page_dec(route="/slack", title="Supercog + Slack", image="home", hide_nav=True, on_load=SlackState.on_page_load)
def slack_page() -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.hstack(
            rx.chakra.image(
                src="/supercog_icon_red.svg",
                height="8rem",
                width="8rem"
            ),
            rx.icon(
                "plus",
                size=60,
                stroke_width="4",
                margin="0 !important"
            ),
            rx.chakra.image(
                src="/slack.svg",
                height="8rem",
                width="8rem",
            ),
            width="100%",
            align_items="center",
            justify_content="center",
            gap="4rem",
            margin_top="5rem",
        ),
        rx.cond(
            SlackState.slack_error,
            rx.chakra.vstack(
                rx.chakra.vstack(
                    rx.chakra.hstack(
                        rx.icon(
                            "triangle-alert",
                            color=rx.color("red", 11)
                        ),
                        rx.heading(
                            "Error installing Supercog into Slack",
                            color_scheme="red"
                        ),
                    ),
                    rx.text(
                        SlackState.slack_error,
                        " Please try again.",
                        size="4"
                    ),
                ),
                slack_install_button(
                    button_text="Try Again",
                    font_size="1.2rem",
                    height="3rem",
                    width="10rem",
                ),
                gap="2rem"
            ),
            rx.cond(
                SlackState.slack_code,
                rx.chakra.vstack(
                    rx.heading(
                        "Installing Supercog into Slack"
                    ),
                    rx.chakra.spinner(thickness=4, size="xl"),
                    gap="3rem"
                ),
                rx.cond(
                    SlackState.is_authenticated & SlackState.has_installed_slack,
                    rx.chakra.vstack(
                        rx.heading(
                            "Successfully installed Supercog into Slack",
                            color_scheme="green"
                        ),
                        rx.chakra.hstack(
                            slack_install_button(),
                            slack_deep_link_button(
                                primary_button=True,
                            ),
                        ),
                        gap="2rem"
                    ),
                    rx.fragment(
                        slack_install_button(
                            button_text="Add Supercog to Slack",
                            font_size="1.5rem",
                            height="5rem",
                            width="24rem",
                        ),
                    ),
                ),
            ),
        ),
        gap="5rem",
    )
