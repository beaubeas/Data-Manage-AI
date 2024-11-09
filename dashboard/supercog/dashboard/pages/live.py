"""The home page of the app."""

from supercog.dashboard import styles
from supercog.dashboard.templates import template
from supercog.dashboard.global_state  import require_google_login

from supercog.dashboard.components.markdown_modal import markdown_modal
from supercog.dashboard.state_models import AgentState
from supercog.dashboard.editor_state import EditorState
from supercog.shared.utils import load_file_content

import reflex as rx

def agent_box(app: AgentState) -> rx.Component:
    return rx.chakra.box(
        rx.chakra.hstack(
            rx.chakra.image(
                src=app.avatar,
                width="64px",
                height="64px",
            ),
            rx.chakra.vstack(
                rx.chakra.link(app.name, font_size="lg", font_weight="bold", href=f"/app/{app.id}"),
                rx.chakra.text(app.description),
                width="100%",
                align_items="flex-start",
            ),
        ),
        border_color="black",
        border_width="1px",
        padding="5px",
        border_radius="5px",
        width="100%",
    )

def stats_box(app: AgentState) -> rx.Component:
    return rx.chakra.vstack(
        rx.markdown("**Trigger**: _" + app.trigger_prefix + "_  \n" + \
            "**Runs today**: " + EditorState.run_counts[app.id] + "  \n" + \
            "**Last run**: " + EditorState.latest_runs[app.id],
            class_name="agent_stats",
        ),
        border_color="black",
        border_width="1px",
        border_radius="5px",
        width="90%",
    )

def log_box(app: AgentState) -> rx.Component:
    return rx.chakra.box(
        rx.foreach(EditorState.agent_logs[app.id], lambda log: rx.chakra.text(log)
        rx.chakra.input(
            value=State.agent_logs[app.id],
            min_height="6em",
        ),
        bg="lightgray",
        width="100%",
    )

def app_box(app: AgentState) -> rx.Component:
    return rx.chakra.grid(
        rx.chakra.grid_item(
            agent_box(app),
            col_span=1,
        ),
        rx.chakra.grid_item(
            stats_box(app),
            col_span=1,
        ),
        rx.chakra.grid_item(
            log_box(app),
            col_span=1,
        ),
        template_columns="3fr 2fr 2fr",
        padding_bottom="10px",
    )

def app_link(app: AgentState) -> rx.Component:
    return rx.chakra.link(
        rx.chakra.button("Edit"),
        href=f"/edit/{app.id}",
    )

@template(route="/live/", title="LLMonster: Live View", image="radio",
          on_load=State.load_current_runs)
@require_google_login
def live_view() -> rx.Component:
    """The live agent view page."""

    return rx.chakra.vstack(
        rx.chakra.heading(rx.chakra.hstack(rx.lucide.icon(tag="radio"), rx.chakra.text("Live Assistants")), size="md"),
        rx.chakra.divider(border_color="black"),
        rx.chakra.text(" ", padding_bottom="20px"),
        rx.foreach(State.live_agent_list, app_box),
        rx.chakra.button("Listen...", on_click=State.wait_for_logs),
        bg=styles.bg_dark_color,
        color=styles.text_light_color,
        min_h="90vh",
        max_height="87vh",
        align_items="stretch",
        spacing="0",
    )
