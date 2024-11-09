import reflex as rx

from supercog.dashboard.global_state import GlobalState

def video_modal(title, video_url: str, 
                   open_flag,
                   close_func,
                   hide_func,
                   ) -> rx.Component:
    return rx.chakra.modal(
            rx.chakra.modal_overlay(
                rx.chakra.modal_content(
                    rx.chakra.modal_header(title),
                    rx.chakra.modal_body(
                        rx.chakra.button(
                            "Close", 
                            size="sm", 
                            position="absolute", 
                            right="10px", 
                            top="10px", 
                            on_click=close_func
                        ),
                        rx.video(
                            url=video_url or "",
                            width="100%",
                            height="75vh",
                            playing=False,
                        ),
                    ),
                    rx.chakra.modal_footer(
                        rx.chakra.button(
                            "I'll watch this later", 
                            color_scheme="blue",
                            on_click=close_func,
                        ),
                        rx.chakra.spacer(),
                        rx.chakra.button(
                            "Don't show this again", 
                            color_scheme="orange",
                            on_click=hide_func
                        ),
                    ),
                    min_width="80vw",
                ),
        ),
        is_open=open_flag,
        size="xl",
    )

def product_tour_button() -> rx.Component:
    return rx.cond(
        GlobalState.show_product_tour | GlobalState.show_sc_tour,
        rx.box(
            rx.chakra.button(
                "Product Tour",
                on_click=GlobalState.toggle_delete_modal(
                    rx.cond(
                        GlobalState.show_product_tour,
                        'tour',
                        'sc_tour',
                    ),
                    ''
                ),
                color_scheme="blue",
                variant="outline",
                size="sm",
            ),
            rx.cond(
                GlobalState.show_product_tour,
                video_modal(
                    "Editor Tour", 
                    "https://youtu.be/U7zwWAEZQ4s",
                    open_flag=GlobalState.open_modals['tour'],
                    close_func=GlobalState.toggle_delete_modal('tour', ''),
                    hide_func=GlobalState.permanently_hide_tour,
                ),
                video_modal(
                    "Supercog Agent Tour", 
                    "https://youtu.be/e6bLFgsqXYM",
                    open_flag=GlobalState.open_modals['sc_tour'],
                    close_func=GlobalState.toggle_delete_modal('sc_tour', ''),
                    hide_func=GlobalState.permanently_hide_sc_tour,
                )
            ),
        ),
    )
