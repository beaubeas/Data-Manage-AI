import reflex as rx
from supercog.dashboard.index_state import IndexState


def generate_avatar_button(appid) -> rx.Component:
    return rx.chakra.button(
            "Generate image",
            is_disabled=IndexState.avatar_generating,
            on_click=lambda: IndexState.toggle_avatar_modal(appid),
            size="sm",
            variant="link",
    )