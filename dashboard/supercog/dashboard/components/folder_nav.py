import reflex as rx

from supercog.dashboard.global_state import GlobalState
from supercog.dashboard.state_models import UIFolder
from supercog.dashboard.components.buttons import icon_button

def dynamic_icon(icon_name):
    return rx.match(
        icon_name,
        ("folder", rx.icon("folder", size=16, flex_shrink="0")),
        ("folder-lock", rx.icon("folder-lock", size=16, flex_shrink="0")),
        ("folder-tree", rx.icon("folder-tree", size=16, flex_shrink="0")),
    )

def editable_nav_button(folder: UIFolder) -> rx.Component:
    return rx.context_menu.root(
        rx.context_menu.trigger(
            icon_button(
                icon=dynamic_icon(folder.folder_icon_tag),
                text=folder.name,
                on_click=rx.redirect(f"/agents/{folder.slug}"),
                max_width="150px",
            ),
        ),
        rx.context_menu.content(
            rx.context_menu.item(
                "Edit", 
                on_click=GlobalState.toggle_edit_folder_modal(folder.name),
            ),
            rx.context_menu.separator(),
            rx.context_menu.item(
                "Delete", 
                color="red",
                on_click=GlobalState.toggle_delete_modal('folder', f"folder:{folder.slug}"),
            ),
        ),
    )

def folder_nav() -> rx.Component:
    return rx.chakra.button_group(
        rx.foreach(
            GlobalState.folders,
            editable_nav_button,
        ),
        width="100%",
        overflow="scroll",
    ),
