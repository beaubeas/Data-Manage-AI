import reflex as rx

from supercog.shared.services import db_connection_string

config = rx.Config(
    app_name="supercog",
    db_url=db_connection_string("dashboard"),
    tailwind={
        "theme": {
            "extend": {
                "screens": {
                    "xs": "450px",
                }
            }
        }
    },
    frontend_packages=[
        "react-icons",
    ],
)
