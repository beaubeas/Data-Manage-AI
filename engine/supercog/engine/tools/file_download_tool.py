from typing import Callable
from urllib.parse import urlparse

import html2text
import requests

from supercog.engine.tool_factory import ToolFactory, ToolCategory

class FileDownloadTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id = "file_download",
            system_name = "File Download",
            help = "Download a file from a link, will convert HTML to text.",
            logo_url="https://static.vecteezy.com/system/resources/previews/000/574/204/original/vector-sign-of-download-icon.jpg",
            auth_config = { },
            category=ToolCategory.CATEGORY_FILES
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.download_url_as_file,
            self.download_file_content,
        ])

    def download_url_as_file(self, url: str, file_name_hint: str="") -> str:
        """ Downloads a file from the web and stores it locally. Returns the
            file name. 
        """
        r = requests.get(url)
        save_file = file_name_hint or self.get_last_path_component(url)

        if r.status_code == 200:
            with open(save_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return save_file
        else:
            return f"Error: {r.status_code} {r.reason}"
        
    def get_last_path_component(self, url: str) -> str:
        # Parse the URL
        parsed_url = urlparse(url)
        # Get the path from the parsed URL
        path = parsed_url.path
        # Split the path and get the last component
        last_component = path.split('/')[-1]
        return last_component
    
    def download_file_content(self, url: str, limit: int=4000) -> str:
        """ Downloads a file from the web and returns its contents directly.
        """
        r = requests.get(url)

        if r.status_code == 200:
            mime_type = r.headers.get('content-type') or ""
            if 'html' in mime_type:
                # Use beautifulsoup to extract text
                return html2text.html2text(r.text)[0:limit]
            else:
                return r.text[0:limit]
        else:
            return f"Error: {r.status_code} {r.reason}"
