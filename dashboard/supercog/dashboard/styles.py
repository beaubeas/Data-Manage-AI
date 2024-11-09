"""Styles for the app."""

import reflex as rx

border_radius = "0.375rem"
box_shadow = "0px 0px 0px 1px rgba(84, 82, 95, 0.14)"
border = "1px solid #F4F3F6"
text_color = "black"
accent_text_color = "#1A1060"
accent_color = "#F5EFFE"
hover_accent_color = {"_hover": {"color": accent_color}}
hover_accent_bg = {"_hover": {"bg": accent_color}}
nav_width="45px"
page_header_height = "36px"
chat_height = "calc(100vh - 260px + 4vh)"

template_page_style = {
    "padding_top": "0em", 
    "padding_x": ["auto", "2em"], 
    "height": f"calc(100vh - {page_header_height} - var(--space-3))",
    "overflow": "hidden",
    # Tailwind class to account for navbar hiding on smaller screens
    "class_name": f"w-[calc(100vw-0.5rem)] md:w-[calc(100vw-{nav_width}-0.5rem)]"
}

slim_template_page_style = {
    "padding_top": "0em", 
    "padding_x": ["auto", "2em"], 
    "height": "100%",
    "width": "100%",
    "overflow": "hidden",
}

template_content_style = {
    "align_items": "flex-start",
    #"box_shadow": box_shadow,
    #"border_radius": border_radius,
    "padding": "0",
    "height":"100%",
}

link_style = {
    "color": text_color,
    "text_decoration": "none",
    **hover_accent_color,
}

overlapping_button_style = {
    "background_color": "white",
    "border": border,
    "border_radius": border_radius,
}

base_style = {
    rx.chakra.MenuButton: {
        "width": "3em",
        "height": "3em",
        **overlapping_button_style,
    },
    rx.chakra.MenuItem: hover_accent_bg,
}

markdown_style = {
    "code": lambda text: rx.chakra.code(text, color="#1F1944", bg="#EAE4FD"),
    "a": lambda text, **props: rx.chakra.link(
        text,
        **props,
        font_weight="bold",
        color="#03030B",
        text_decoration="underline",
        text_decoration_color="#AD9BF8",
        _hover={
            "color": "#AD9BF8",
            "text_decoration": "underline",
            "text_decoration_color": "#03030B",
        },
    ),
}

# copied from the Chat app
border_color = "#888" #"#fff3"
shadow_light = "rgba(17, 12, 46, 0.15) 0px 48px 100px 0px;"
message_style = dict(display="inline-block", border_radius="xl", margin="1px")
bg_medium_color = "#FFF"
input_style = dict(
    bg=bg_medium_color,
    border_color=border_color,
    border_width="0px",
    p="4",
)
bg_dark_color = "#FFF"
text_light_color = "#444"
