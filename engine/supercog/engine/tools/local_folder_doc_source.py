from typing import AsyncGenerator
import os

from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.engine.doc_source_factory import DocSourceFactory

class LocalFolderDocSource(DocSourceFactory):
    def __init__(self):
        super().__init__(
            id = "local_file_source",
            system_name = "Docs from Local Files",
            logo_url=super().logo_from_domain("atlassian.com"),
            category=ToolCategory.CATEGORY_DOCSRC,
            auth_config = {
                "strategy_token": {
                    "local_folder": "Path to local folder",
                    "help": ""
                },
            },
            help="""
Local documents from a local folder
""",

        )

    def get_documents(self, folder_id: str, **kwargs) -> AsyncGenerator[str, None]:
        """ Yields a list of documents from the indicated folder. """
        folder_path = self.credentials.get("local_folder")
        for file in os.listdir(folder_path):
            yield open(os.path.join(folder_path, file)).read()
