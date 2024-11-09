import reflex as rx
from typing import Any

class XMLViewer(rx.Component):
    """XML Viewer component."""
    
    library = "react-xml-viewer"  # The npm package name
    tag = "XMLViewer"  # The component name in the package
    is_default = True  # Indicates if it is a default export

    # Example props the component might take
    xml: rx.Var[Any]
    collapsible: bool =True
    initalCollapsedDepth: int= 1
    
# Convenience function to create the XMLViewer component.
xml_viewer = XMLViewer.create

'''
# Use the XMLViewer component in your app.
def index():
    sample_xml = "<root><child>Sample XML</child></root>"
    return xml_viewer(xml=sample_xml)

app = rx.App()
app.add_page(index)
'''
