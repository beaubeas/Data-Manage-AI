import reflex as rx

from supercog.dashboard.global_state import GlobalState
from supercog.dashboard.components.slack_buttons import slack_install_button

def slack_success_modal() -> rx.Component:
    return rx.chakra.modal(
            rx.chakra.modal_overlay(
                rx.chakra.modal_content(
                    rx.chakra.modal_header(
                        rx.hstack(
                            rx.image(src="/slack.svg"),
                            rx.chakra.heading("Slack Next Steps", size="lg"),
                            align="center",
                            gap="1rem"
                        )
                    ),
                    rx.chakra.modal_body(
                        rx.vstack(
                            rx.chakra.heading("1. Add Supercog to your workspace", size="md"),
                            rx.text(
                                "Add Supercog to your workspace by clicking ",
                                rx.text.strong("+ Add apps", font_weight="bold"),
                                " in Slack's sidebar"
                            ),
                            rx.image(src="/slack_add_app.png", max_height="200px", align_self="center"),
                            rx.chakra.heading("2. Interact with Supercog", size="md"),
                            rx.list.unordered(
                                rx.list.item(
                                    rx.text(
                                        "Chat with Supercog AI directly",
                                    )
                                ),
                                rx.list.item(
                                    rx.text(
                                        "Mention Supercog in a channel with ",
                                        rx.code("@Supercog AI", color_scheme="blue")
                                    )
                                ),
                                rx.list.item(
                                    rx.text(
                                        "Add Supercog AI to the top bar to use as an assistant"
                                    ),
                                    rx.image(src="/slack_top_bar.png", max_height="150px", align_self="center"),
                                ),
                                rx.list.item(
                                    rx.text(
                                        "Use Supercog AI side by side with channels"
                                    ),
                                    rx.image(src="/slack_side_by_side.png", max_height="350px", align_self="center"),
                                ),
                            ),
                            gap="1rem",
                        ),
                        overflow="scroll"
                    ),
                    rx.chakra.modal_footer(
                        rx.hstack(
                            slack_install_button(),
                            rx.chakra.button(
                                "Close", 
                                color_scheme="green",
                                on_click=GlobalState.toggle_delete_modal("slack_success", "")
                            ),
                            justify="between",
                            width="100%",
                        )
                    ),
                    max_height="80%",
                    overflow="hidden",
                ),
        ),
        is_open=GlobalState.open_modals["slack_success"],
        size="xl",
    )

def slack_failure_modal() -> rx.Component:
    return rx.chakra.modal(
            rx.chakra.modal_overlay(
                rx.chakra.modal_content(
                    rx.chakra.modal_header(
                        rx.hstack(
                            rx.image(src="/slack.svg"),
                            rx.chakra.heading("Issue Installing to Slack", size="lg"),
                            align="center",
                            gap="1rem"
                        )
                    ),
                    rx.chakra.modal_body(
                        rx.text("There was an error installing Supercog AI in Slack."),
                    ),
                    rx.chakra.modal_footer(
                        rx.chakra.hstack(
                            rx.chakra.button(
                                "Close", 
                                on_click=GlobalState.toggle_delete_modal("slack_failure", "")
                            ),
                            slack_install_button(primary_button=True, button_text="Try Again"),
                            width="100%",
                            justify_content="flex-end"
                        )
                    ),
                ),
        ),
        is_open=GlobalState.open_modals["slack_failure"],
        size="lg",
    )
