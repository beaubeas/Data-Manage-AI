from typing import AsyncGenerator, List
import os
from llama_index.readers.notion import NotionPageReader
from llama_index.core import Document

from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.engine.doc_source_factory import DocSourceFactory
from pydantic import Field
import requests
import json
from datetime import datetime

class NotionDocSource(DocSourceFactory):
    reader: NotionPageReader = Field(default=None)

    def __init__(self):
        super().__init__(
            id = "notion_file_source",
            system_name = "Docs from Notion",
            logo_url=super().logo_from_domain("notion.com"),
            category=ToolCategory.CATEGORY_DOCSRC,
            auth_config = {
                "strategy_token": {
                    "internal_integration_token": "Notion Internal Integration Token",
                },
            },
            help="""
Load documents from Notion (Connection must be established with pages!)
""",

        )

    async def get_documents(self, folder_id: str=None, **kwargs) -> AsyncGenerator[Document, None]:
        """
        Returns a list of documents from Notion.
        """
        try:
            if not self.reader:
                internal_integration_token = self.credentials.get("internal_integration_token")
                if not internal_integration_token:
                    raise ValueError("Notion integration token is not provided")
                self.reader = NotionPageReader(integration_token=internal_integration_token)

            pages = self.reader.list_pages()
            doc = self.reader.load_data(page_ids=pages)

            try:
                #LlamaIndex Notion Reader doesn't provide title. Directly calling notion api to obtain title and update metadata.
                counter = 0
                for pageid in pages:
                    url = 'https://api.notion.com/v1/pages/' + pageid
                    headers = {
                        'Notion-Version': '2022-06-28',
                        'Authorization': 'Bearer ' + internal_integration_token}
                    response = requests.get(url, headers=headers)
                    data = json.loads(response.text)

                    title = data['properties']['title']['title'][0]['text']['content']
                    creation_date = data['created_time']
                    last_modified_date = data['last_edited_time']

                    doc[counter].metadata = {
                        "file_path": "notion",
                        "file_name": title,
                        "file_type": "text/plain",
                        "file_size": len(doc[counter].text),
                        "creation_date": creation_date,
                        "last_modified_date": last_modified_date,
                        "page_id": pageid
                    }
                    
                    counter += 1
            except:
                current_date = datetime.utcnow().isoformat()
                counter = 0
                for pageid in pages:
                    doc[counter].metadata = {
                        "file_path": "notion",
                        "file_name": "notion",
                        "file_type": "text/plain",
                        "file_size": len(doc[counter].text),
                        "creation_date": current_date,
                        "last_modified_date": current_date,
                        "page_id": pageid
                    }
                    
                    counter += 1
            
            yield doc
        except Exception as e:
            raise RuntimeError(f"Error fetching Notion documents: {str(e)}")
