"""The App view page."""
from supercog.dashboard import styles
from supercog.dashboard.templates import template
from supercog.dashboard.guest_state import GuestState
from supercog.dashboard.connections_state import ConnectionsState

#from supercog.dashboard.components.guest_chat import guest_chat_window
from supercog.dashboard.templates.template import custom_page_dec

import reflex as rx

@custom_page_dec(route="/guest/[agentid]/", title="Supercog Intro", 
                 image="home", hide_nav=True, on_load=GuestState.on_page_load)
def guest_page() -> rx.Component:
    """
    Returns:
        The Supercog default home experience
    """
    return rx.chakra.box(
        rx.chakra.vstack(
            rx.chakra.hstack(
                rx.chakra.heading(GuestState.app.name, font_size="lg", margin_bottom="10px"),
                rx.chakra.spacer(),
                rx.chakra.spacer(max_width="160px"),
                align_items="stretch",
                width="100%",
                id="rest_after_header",
            ),
#            guest_chat_window(GuestState.app),
            rx.script(src="/custom.js"), 
            bg=styles.bg_dark_color,
            color=styles.text_light_color,
            height="100%",
            id="edit-app",
            spacing="0",
            align_items="stretch",
            class_name="edge_bleed",
        ),
        width="80vw",
        height="80vh",
        position="absolute",
        left="50%",
        top="0",
        transform="translateX(-50%)",
    )
