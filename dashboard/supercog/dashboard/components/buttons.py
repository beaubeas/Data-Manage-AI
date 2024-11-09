import reflex as rx
from typing import Callable

def icon_button(
    icon: rx.Component,
    text: str,
    rx_color_family: str = "indigo",
    rx_bg_weight: str = 4,
    rx_text_weight: str = 11,
    on_click: Callable = None,
    **kwargs
) -> rx.Component:
    return rx.hstack(
        icon,
        rx.text(
            text,
            font_weight="600",
            class_name="chakra_transistion lines-2 webkit-max-lines",
        ),
        border_radius="0.5rem",
        padding="1rem",
        background_color=rx.color(rx_color_family, rx_bg_weight),
        color=rx.color(rx_color_family, rx_text_weight),
        cursor="pointer",
        on_click=on_click,
        _hover={
            "backgroundColor": rx.color(rx_color_family, rx_bg_weight + 1),
            "color": rx.color(rx_color_family, rx_text_weight + 1),
        },
        align="center",
        **kwargs
    )

def link_button(
    icon: rx.Component,
    text: str,
    href: str,
    external_link: bool = False,
    **kwargs
) -> rx.Component:
    target = "_blank" if external_link else "_self"
    return rx.link(
        icon_button(
            icon=icon,
            text=text,
            **kwargs
        ),
        href=href,
        target=target,
        text_decoration="none",
        user_selct="none",
    ),