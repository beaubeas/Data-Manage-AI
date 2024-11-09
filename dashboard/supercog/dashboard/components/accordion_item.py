import reflex as rx

def accordion_item(header: rx.Component, content: rx.Component, header_kwargs: dict = {}, show_border: bool = False) -> rx.Component:
    return rx.chakra.accordion_item(
        rx.chakra.accordion_button(
            header,
            justify_content="space-between",
            **header_kwargs,
        ),
        rx.chakra.accordion_panel(
            content,
        ),
        border=rx.cond(
            show_border,
            "",
            "none",
        )
    ),
