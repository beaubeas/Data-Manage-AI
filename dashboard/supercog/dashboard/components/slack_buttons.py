import reflex as rx
from typing import Optional

from supercog.dashboard.global_state import GlobalState
from supercog.dashboard.slack_state import SlackState

def slack_header_button() -> rx.Component:
  return rx.cond(
        GlobalState.has_installed_slack,
        rx.chakra.button(
            rx.image(src="/slack.svg", margin_right="0.5rem"),
            "Slack Help",
            on_click=GlobalState.toggle_delete_modal("slack_success", ""),
            color_scheme="blue",
            variant="outline",
            size="sm",
        ),
        rx.chakra.button(
            rx.image(src="/slack.svg", margin_right="0.5rem"),
            "Add Supercog to Slack",
            color_scheme="blue",
            variant="outline",
            size="sm",
            on_click=SlackState.call_install_slack,
        ),
    )

def slack_install_button(primary_button: bool = False, button_text: str = "Add to a new workspace", font_size: Optional[str] = None, **kwargs) -> rx.Component:
  return rx.chakra.button(
        rx.cond(
            primary_button,
            rx.fragment(),
            rx.image(
                src="/slack.svg",
                margin_right="0.5rem",
                height=font_size,
                width=font_size,
            ),
        ),
        rx.chakra.text(
            button_text,
            font_size=font_size
        ),
        color_scheme="blue",
        variant=rx.cond(
            primary_button,
            "solid",
            "outline"
        ),
        size="md",
        on_click=SlackState.call_install_slack,
        **kwargs
    ),

def slack_deep_link_button(primary_button: bool = False, button_text: str = "Go to Slack!", font_size: Optional[str] = None, **kwargs) -> rx.Component:
  return rx.chakra.button(
        rx.cond(
            primary_button,
            rx.fragment(),
            rx.image(
                src="/slack.svg",
                margin_right="0.5rem",
                height=font_size,
                width=font_size,
            ),
        ),
        rx.chakra.text(
            button_text,
            font_size=font_size
        ),
        color_scheme="blue",
        variant=rx.cond(
            primary_button,
            "solid",
            "outline"
        ),
        size="md",
        on_click=SlackState.call_deep_link_to_slack,
        **kwargs
    ),
