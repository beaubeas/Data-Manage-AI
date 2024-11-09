import reflex as rx

def spinner(transparent: bool = False, **kwargs) -> rx.Component:
    return rx.chakra.image(
        src=rx.cond(
            transparent,
            "/GIF6-transparent.gif",
            "/GIF6.gif",
        ),
        height="auto",
        **kwargs,
    )
