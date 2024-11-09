from typing import AsyncGenerator, Optional
from supercog.shared.services import config, get_public_service_domain

from llama_index.core import Document

from .tool_factory import ToolFactory
from .db import DocSourceConfig

class DocSourceFactory(ToolFactory):
    def __init__(self, **kwargs):
        super().__init__(**kwargs | {"is_docsource": True})

    def get_tools(self) -> list:
        return []
    
    # Return an oauth style authorize link
    async def get_authorize_url(self, tenant_id: str, user_id: str, index_id: str, source_id: str) -> str:
        pass

    # After oauth callback is complete then callback args will be passed here. But they are already
    # stored on the DocSourceConfig so this is optional.
    async def authorize_callback(self, params: dict):
        pass

    async def get_documents(self, folder_id: str, **kwargs) -> AsyncGenerator[Document, None]:
        """ Yields a list of documents from the indicated folder. """
        pass

    @staticmethod
    def get_doc_factory(doc_source: DocSourceConfig) -> "DocSourceFactory":
        from supercog.engine.all_tools import FACTORY_MAP

        if doc_source.tool_factory_id in FACTORY_MAP:
            doc_factory = FACTORY_MAP.get(doc_source.tool_factory_id).__class__()
            doc_factory.credentials = doc_source.retrieve_secrets()

            return doc_factory
        else:
            raise RuntimeError(f"Factory {doc_source.tool_factory_id} not found")
