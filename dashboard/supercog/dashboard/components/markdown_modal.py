import reflex as rx

from supercog.dashboard.state_models import AgentState
from supercog.dashboard.global_state import GlobalState

def markdown_modal(title, content, 
                   open_flag=GlobalState.markdown_modal_open,
                   close_func=GlobalState.toggle_markdown_modal,
                   video_url: str = None) -> rx.Component:
    height="500px"
    video_url = None
    if video_url:
        height="250px"
    return rx.chakra.modal(
            rx.chakra.modal_overlay(
                rx.chakra.modal_content(
                    rx.chakra.modal_header(title),
                    rx.chakra.modal_body(
                        rx.markdown(
                            content,
                            max_height=height,
                            overflow="scroll",
                        ),
                        width="600px",
                    ),
                    rx.cond(
                        video_url is not None,
                        rx.vstack(
                            rx.text("scroll ⇣"),
                            rx.video(
                                url=video_url or "",
                                width="560px",
                                #padding_left="20px",
                                height="300px",
                            ),
                            align_items="center",
                        ),
                    ),
                    rx.chakra.modal_footer(
                        rx.chakra.button("Close", on_click=close_func),
                    ),
                    min_width="610px",
                ),
        ),
        is_open=open_flag,
        size="xl",
    )
