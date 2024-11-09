from pathlib import Path

import reflex as rx


from supercog.dashboard.templates import template
from supercog.dashboard.admin_state import AdminState

def runs_list() -> rx.Component:
    return rx.data_table(
        data=AdminState.runs_df,
        pagination=True,
        search=True,
        sort=True,
    )

def agents_list() -> rx.Component:
    return rx.data_table(
        data=AdminState.agents_df,
        pagination=True,
        search=True,
        sort=True,
    )

def info_box() -> rx.Component:
    return rx.chakra.box(
        rx.heading("Info", size="2"),
        rx.data_table(
            data=AdminState.agents_info,
            pagination=False,
            search=False,
            sort=False,
        ),
        width="300px",
    )

@template(route="/admin", title="Supercog: Admin", image="circle_help", on_load=AdminState.admin_page_load, hide_nav=True)
def admin_page() -> rx.Component:
    """The Admin page.
    """

    return rx.chakra.vstack(
        rx.cond(
            AdminState.is_hydrated,
            rx.chakra.vstack(
                rx.chakra.button("Refresh", on_click=AdminState.admin_page_load, size="sm"),
                info_box(),
                rx.heading("Live agents", size="2"),
                agents_list(),
                rx.heading("Latest Runs", size="2"),
                runs_list(),
                align_items="flex-start",
            ),
            rx.chakra.spinner(),
        ),
    )
    

