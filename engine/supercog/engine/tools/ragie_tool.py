from typing import List, Callable, ClassVar
import traceback
from supercog.engine.tool_factory import ToolFactory, LLMFullResult, ToolCategory
from supercog.shared.services import config
from supercog.shared.models import DocIndexReference
from ragie import Ragie
from sqlmodel import Session, select
import pandas as pd
from ..db import DocIndex
from ..rag_utils import lookup_index, get_user_personal_index, get_ragie_partition
from ..jwt_auth import User as JWTUser
from supercog.shared.services import db_connect

class RagieTool(ToolFactory):
    ragie: ClassVar[Ragie] = Ragie(auth=config.get_global('RAGIE_API_KEY', required=False) or "")

    def __init__(self, **kwargs):
        if kwargs:
            super().__init__(**kwargs)
        else:
            super().__init__(
                id="ragie_functions",
                system_name="Knowledge Index Search",
                logo_url="https://upload.wikimedia.org/wikipedia/commons/8/86/Database-icon.svg",
                auth_config={},
                category=ToolCategory.CATEGORY_GENAI,
                help="""Searches for content in knowledge indices.""",
            )

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            self.list_documents,
            self.search_knowledge_index,
        ])

    # def add_document(self, index_id: str = None, file_name: str = None, content: bytes = None) -> str:
    #     """Add a document to the specified index.
        
    #     Args:
    #         index_id: The ID of the index to add the document to (optional, uses personal index if not provided)
    #         file_name: Name of the file being added
    #         content: Content of the document as bytes
            
    #     Returns:
    #         Confirmation message of document addition
    #     """
    #     user = User(user_id=self.run_context.user_id, tenant_id=self.run_context.tenant_id)

    #     try:
    #         if index_id is None:
    #             index_id = self.get_personal_index_id()

    #         partition = get_ragie_partition(user)
    #         response = self.ragie.documents.create(
    #             request={
    #                 "file": {
    #                     "file_name": file_name,
    #                     "content": content,
    #                 },
    #                 "metadata": {
    #                     "tenant_id": self.run_context.tenant_id,
    #                     "user_id": self.run_context.user_id,
    #                     "index_id": index_id
    #                 },
    #                 "partition": partition,
    #             }
    #         )
            
    #         return LLMFullResult(f"Document '{file_name}' successfully added to index {index_id}")
    #     except Exception as e:
    #         return f"Error adding document: {str(e)}"

    def list_documents(
            self, 
            index_name: str = "personal",
            page: int = 1,
            page_size: int = 10
        ) -> str:
        """List documents in the specified index.
        
        Args:
            index_id: The ID of the index to list documents from (optional, uses personal index if not provided)
            page: Page number (default: 1)
            page_size: Number of documents per page (default: 10)
            
        Returns:
            List of documents in the index
        """
        try:
            #if index_id is None:
            with self.run_context.get_db_session() as session:
                index = get_user_personal_index(
                    self.run_context.get_user_object(), 
                    session
                )
            if index:
                index_id = index.id
            else:
                return "Personal index not found."

            partition = get_ragie_partition(self.run_context.tenant_id, index_id)
            response = self.ragie.documents.list(
                request={
                    "filter": {
                        "$eq": ["partition", partition]
                    },
                    "page_size": page_size
                }
            )
            
            current_page = 1
            next_func = response.next
            
            # Navigate to the requested page
            while current_page < page and next_func and len(response.result.documents) == page_size:
                try:
                    response = next_func()
                    next_func = response.next
                    current_page += 1
                except Exception as e:
                    return f"Error navigating pages: {str(e)}"

            if current_page == page:
                documents = response.result.documents
                if documents:
                    # Format the document list in a readable way
                    doc_list = [f"- {doc.name} (ID: {doc.id})" for doc in documents]
                    return LLMFullResult(f"Documents in index {index_id} (Page {page}):\n" + "\n".join(doc_list))
                else:
                    return "No documents found or page is empty."
            else:
                return "Requested page not available."

        except Exception as e:
            return f"Error listing documents: {str(e)}"

    def search_knowledge_index(
            self, 
            index_name: str = "personal", 
            threshold: float = 0.1,
            query: str = None
        ) -> dict:
        """Search for documents in the given named index. Provide threshold to determine
            how relevant the search results should be."""
        try:
            index: DocIndexReference|None = self.run_context.find_doc_index_by_name(index_name)
            if index is None:
                avail = ",".join([i.name for i in self.run_context.get_doc_indexes()])
                return f"Index {index_name} not found. Available indexes: {avail}."

            partition = get_ragie_partition(self.run_context.tenant_id, index.index_id)
            response = self.ragie.retrievals.retrieve(
                request = {
                    "query": query,
                    "partition": partition,
                    # "top_k": 10
                }
            )
            # framework will automatically convert list[dict] into a Dataframe (preview)

            # The logic here to first take matching chunks, but then add other chunks from the same
            # documents to fill out the list. I found this necessary for spreadsheets.
            results = []
            docs_added = set()
            for chunk in response.scored_chunks:
                if chunk.score >= threshold:
                    results.append(chunk.model_dump())
                    docs_added.add(chunk.document_id)

            for chunk in response.scored_chunks:
                if chunk.score < threshold and chunk.document_id in docs_added:
                    results.append(chunk.model_dump())

            df = pd.DataFrame(results)
            return self.get_dataframe_preview(df, max_rows=8)

        except Exception as e:
            traceback.print_exc()
            return f"Error searching documents: {str(e)}" 