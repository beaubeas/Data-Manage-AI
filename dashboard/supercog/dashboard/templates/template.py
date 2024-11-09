"""Common templates used between pages in the app."""

from __future__ import annotations
from typing import Callable, Any

from supercog.shared.services import config

from supercog.dashboard import styles
from supercog.dashboard.components.sidebar import sidebar
from supercog.dashboard.components.modal import confirm_delete_folder
from supercog.dashboard.components.video_tour import product_tour_button
from supercog.dashboard.components.slack_buttons import slack_header_button
from supercog.dashboard.components.slack_modals import slack_success_modal, slack_failure_modal
from supercog.dashboard.global_state import GlobalState
from supercog.dashboard.slack.utils.slack_modes import is_events_mode

from reflex.config import get_config
import reflex as rx

# Meta tags for the app.
default_meta = [
    {
        "name": "viewport",
        "content": "width=device-width, shrink-to-fit=no, initial-scale=1",
    },
]

def google_tags() -> rx.Component:
    return rx.fragment(
        rx.script(
            src="https://www.googletagmanager.com/gtag/js?id=G-LWHYWY10PQ", 
            strategy="afterInteractive"
        ),
        rx.script("""
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());

            gtag('config', 'G-LWHYWY10PQ');
        """),
    )

def user_info() -> rx.Component:
    return rx.chakra.hstack(
        rx.cond(
            is_events_mode() | config.is_prod(),
            slack_header_button(),
        ),
        product_tour_button(),
        rx.chakra.vstack(
            rx.chakra.popover(
                rx.chakra.popover_trigger(
                    rx.chakra.button(GlobalState.authenticated_user.name, size="sm")
                ),
                rx.chakra.popover_content(
                    rx.chakra.link(
                        rx.chakra.button("Settings", size="sm", variant="outline", width="100%"),
                        href="/settings",
                        width="100%",
                    ),
                    rx.link(
                        rx.chakra.button("Logout", size="sm", variant="outline", width="100%"),
                        href="/",
                        on_click=GlobalState.do_logout,
                        width="100%",
                    ),
                    width="160px",
                ),
            ),
            align_items="flex-start",
        ),
        rx.chakra.avatar(
            name=GlobalState.authenticated_user.name,
            src=GlobalState.authenticated_user.profileurl,
            size="sm",
        ),
    )

def user_domain() -> rx.Component:
    return rx.chakra.heading(
        rx.chakra.link(
            GlobalState.orgname,
            text_decoration="none",
            href="/home"
        ),
        size="sm"
    )

def page_header() -> rx.Component:
    return rx.chakra.hstack(
        rx.box(
            rx.cond(GlobalState.is_authenticated,
                user_domain(),
            ),
            flex="1",
            display="flex",
            justify_content="flex-start",
            align_items="center",
        ),
        rx.chakra.link(
            rx.chakra.image(
                src=GlobalState.logo,
                height="2em",
            ),
            href="/home",
        ),
        rx.box(
            rx.chakra.menu(
                rx.cond(GlobalState.is_authenticated,
                    user_info(),
                ),
            ),
            flex="1",
            display="flex",
            justify_content="flex-end",
            align_items="center",
        ),
        z_index="500",
        align_items="center",
        width="100%",
        justify_content="space-between",
        padding_right="0.5rem",
        height=styles.page_header_height,
    )

def slim_header() -> rx.Component:
    return rx.chakra.hstack(
        # rx.cond(GlobalState.token_is_valid & GlobalState.tokeninfo["email"],
        #     user_domain(GlobalState.tokeninfo),
        # ),
        rx.spacer(),
        rx.chakra.link(
            rx.chakra.image(
                src=GlobalState.logo,
                height="2em",
            ),
            href="/agents",
        ),
        rx.spacer(),
        top="0em",
        z_index="500",
        align_items="center",
        width="100%",
    )

from reflex.page import DECORATED_PAGES

def custom_page_dec(
    route: str | None = None,
    title: str | None = None,
    image: str | None = None,
    hide_nav: bool = False,
    description: str | None = None,
    meta: str | None = None,
    script_tags: list[Any] | None = None,
    on_load: Any | list[Any] | None = None,
):
    """Decorate a function as a page.

    rx.App() will automatically call add_page() for any method decorated with page
    when App.compile is called.

    All defaults are None because they will use the one from add_page().

    Note: the decorated functions still need to be imported.

    Args:
        route: The route to reach the page.
        title: The title of the page.
        image: The favicon of the page.
        description: The description of the page.
        meta: Additionnal meta to add to the page.
        on_load: The event handler(s) called when the page load.
        script_tags: scripts to attach to the page

    Returns:
        The decorated function.
    """

    def decorator(render_fn):
        kwargs = {}
        if route:
            kwargs["route"] = route
        if title:
            kwargs["title"] = title
            
        if image:
            kwargs["image"] = image
        if description:
            kwargs["description"] = description
        if hide_nav:
            kwargs["description"] = "hide"

        if meta:
            kwargs["meta"] = meta
        if script_tags:
            kwargs["script_tags"] = script_tags
        if on_load:
            kwargs["on_load"] = on_load

        DECORATED_PAGES[get_config().app_name].append((render_fn, kwargs))

        return render_fn

    return decorator


def template(
    route: str | None = None,
    title: str | None = None,
    image: str | None = None,
    hide_nav: bool = False,
    description: str | None = None,
    meta: str | None = None,
    script_tags: list[rx.Component] | None = None,
    on_load: rx.event.EventHandler | list[rx.event.EventHandler] | None = None,
) -> Callable[[Callable[[], rx.Component]], rx.Component]:
    """The template for each page of the app.

    Args:
        route: The route to reach the page.
        title: The title of the page.
        image: The favicon of the page.
        description: The description of the page.
        meta: Additionnal meta to add to the page.
        on_load: The event handler(s) called when the page load.
        script_tags: Scripts to attach to the page.

    Returns:
        The template with the page content.
    """

    def decorator(page_content: Callable[[], rx.Component]) -> rx.Component:
        """The template for each page of the app.

        Args:
            page_content: The content of the page.

        Returns:
            The template with the page content.
        """
        # Get the meta tags for the page.
        all_meta = [*default_meta, *(meta or [])]

        @custom_page_dec(
            route=route,
            title=title,
            image=image,
            hide_nav=hide_nav,
            description=description,
            meta=all_meta,
            script_tags=script_tags,
            on_load=on_load,
        )
        def templated_page() -> rx.Component:
            return rx.chakra.hstack(
                google_tags(),
                sidebar(),
                rx.vstack(
                    rx.cond(
                        GlobalState.service_status != "",
                        rx.box(
                            rx.callout(
                                GlobalState.service_status, 
                                icon="triangle_alert", 
                                color_scheme="red",
                                width="100%",
                                padding="4px",
                            ),
                            width="100%",
                            background_color="white",
                            style={"position": "fixed", "z-index": "100000"},
                        ),
                    ),
                    page_header(),
                    rx.chakra.box(
                        rx.chakra.box(
                            page_content(),
                            **styles.template_content_style,
                        ),
                        **styles.template_page_style,
                        id="page_container",
                    ),
                    flex="1",
                ),
                confirm_delete_folder(),
                slack_success_modal(),
                slack_failure_modal(),
                # error_popup_modal(),
                align_items="flex-stretch",
                transition="left 0.5s, width 0.5s",
                position="relative",
                width="100vw",
                height="100vh",
            )

        return templated_page

    return decorator


def slim_template(
    route: str | None = None,
    title: str | None = None,
    image: str | None = None,
    hide_nav: bool = False,
    description: str | None = None,
    meta: str | None = None,
    script_tags: list[rx.Component] | None = None,
    on_load: rx.event.EventHandler | list[rx.event.EventHandler] | None = None,
) -> Callable[[Callable[[], rx.Component]], rx.Component]:

    def decorator(page_content: Callable[[], rx.Component]) -> rx.Component:
        """The template for each page of the app.

        Args:
            page_content: The content of the page.

        Returns:
            The template with the page content.
        """
        # Get the meta tags for the page.
        all_meta = [*default_meta, *(meta or [])]

        @custom_page_dec(
            route=route,
            title=title,
            image=image,
            hide_nav=hide_nav,
            description=description,
            meta=all_meta,
            script_tags=script_tags,
            on_load=on_load,
        )
        def templated_page() -> rx.Component:
            return rx.chakra.hstack(
                rx.vstack(
                    rx.cond(
                        GlobalState.service_status != "",
                        rx.callout(
                            GlobalState.service_status, 
                            icon="triangle_alert", 
                            color_scheme="red",
                            width="100%",
                            padding="4px",
                        ),
                    ),
                    slim_header(),
                    rx.chakra.box(
                        rx.chakra.box(
                            page_content(),
                            **styles.template_content_style,
                        ),
                        **styles.slim_template_page_style,
                        id="page_container",
                    ),
                    flex="1",
                ),
                confirm_delete_folder(),
                slack_success_modal(),
                slack_failure_modal(),
                # error_popup_modal(),
                align_items="flex-stretch",
                transition="left 0.5s, width 0.5s",
                position="relative",
                width="100vw",
                height="100vh",
            )

        return templated_page

    return decorator
