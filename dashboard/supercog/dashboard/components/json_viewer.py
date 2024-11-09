from typing import Any
import reflex as rx

class JsonViewer(rx.Component):
    library = "view-json-react"
    tag = "JsonViewer"

    data: rx.Var[Any]
    expandLevel: int = 1

jsonviewer = JsonViewer.create


