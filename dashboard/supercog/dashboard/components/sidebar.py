"""Sidebar component for the app."""
from supercog.dashboard import styles

import reflex as rx

def sidebar_item(text: str, icon: str, url: str) -> rx.Component:
    """Sidebar item.

    Args:
        text: The text of the item.
        icon: The icon of the item.
        url: The URL of the item.

    Returns:
        rx.Component: The sidebar item component.
    """
    # Whether the item is active.
    active = (rx.State.router.page.path == f"/{text.lower()}") | (
        (rx.State.router.page.path == "/") & text == "Home"
    )

    return rx.link(
        rx.chakra.hstack(
            rx.chakra.tooltip(
                rx.lucide.icon(tag=icon, size=18, padding="0"),
                label=text[9:],
            ),
            #rx.chakra.text(
            #    text,
            #),
            bg=rx.cond(
                active,
                styles.accent_color,
                "transparent",
            ),
            color=rx.cond(
                active,
                styles.accent_text_color,
                styles.text_color,
            ),
            border_radius=styles.border_radius,
            #box_shadow=styles.box_shadow,
            width="100%",
            padding="0",
            margin_bottom="2em",
        ),
        href=rx.cond(url == "/xhelp", "https://github.com/supercog-ai/community/wiki", url),
        target=rx.cond(url == "/xhelp", "_blank", ""),
        border="0",
        width="100%",
    )

def sidebar() -> rx.Component:
    """The sidebar.

    Returns:
        The sidebar component.
    """
    # Get all the decorated pages and add them to the sidebar.
    from reflex.page import get_decorated_pages

    return rx.chakra.box(
        rx.chakra.vstack(
            rx.chakra.vstack(
                *[
                    sidebar_item(
                        text=page.get("title", page["route"].strip("/").capitalize()),
                        icon=page.get("image", "/github.svg"),
                        url=page["route"],
                    )
                    for page in get_decorated_pages() if page.get("description") != "hide"
                ],
                width="100%",
                overflow_y="auto",
                align_items="flex-start",
                padding="1em",
            ),
            rx.chakra.spacer(),
            height="100dvh",
        ),
        display=["none", "none", "block"],
        height="100%",
        position="sticky",
        top="0px",
        border_right=styles.border,
        width=styles.nav_width,
    )
