import reflex as rx

from supercog.dashboard.ragindex_state import RAGIndexState

def doc_source_modal() -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header("Configure Document Source"),
                rx.chakra.modal_body(
                    rx.chakra.form(
                        rx.chakra.select(rx.foreach(RAGIndexState.doc_sources, 
                            lambda src: rx.chakra.option(src.name, 
                                                    value=src.id),
                            ),
                            on_change=RAGIndexState.set_docsource_config_value('doc_source_id'),
                        ),
                        rx.chakra.heading("Folder IDs",  size="sm"),
                        rx.chakra.input(
                            placeholder="Comma separated list of folder IDs",
                            value=RAGIndexState.doc_source.folder_ids,
                            on_change=RAGIndexState.set_docsource_config_value('folder_ids'),
                        ),
                        rx.chakra.heading("File Patterns", size="sm"),
                        rx.chakra.input(
                            placeholder="Comma separated list of file patterns",
                            value=RAGIndexState.doc_source.file_patterns,
                            on_change=RAGIndexState.set_docsource_config_value('file_patterns'),
                        ),
                    ),
                    class_name="vspacing",
                ),
                rx.chakra.modal_footer(
                    rx.chakra.hstack(
                        rx.chakra.button(
                            "Save",
                            color_scheme="blue",
                            on_click=RAGIndexState.save_docsource_config,
                        ),
                        rx.chakra.button(
                            "Cancel", 
                            on_click=RAGIndexState.toggle_doc_source_modal,
                        ),
                        justify_content="space-between",
                    ),
                ),
                min_width="620px",
            ),
        ),
        is_open=RAGIndexState.doc_source_modal_open,
        size="md",
    )
