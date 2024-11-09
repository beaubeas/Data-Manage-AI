import reflex as rx

class PdfDocument(rx.Component):
    """PDF Document component from react-pdf"""

    library = "react-pdf@8.0.2"
    tag = "Document"
    lib_dependencies: list[str] = ["pdfjs-dist@3.11.174"]
    file: rx.Var[str]

    def add_imports(self):
        return {"react-pdf": ["pdfjs"]}

    def add_custom_code(self) -> list[str]:
        return [
            """
        pdfjs.GlobalWorkerOptions.workerSrc = new URL('node_modules/pdfjs-dist/build/pdf.worker.min.js',
            import.meta.url,
        ).toString();
        """
        ]