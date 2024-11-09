import asyncio
from typing import Callable, List, Dict, Optional, Union, Tuple
import requests
from io import StringIO, BytesIO
import numpy as np
from dataclasses import dataclass, field
import pandas as pd
import chardet
import html2text
import json
import os
import re
from langchain_community.document_loaders import PyPDFLoader
import tempfile
import csv
import mimetypes
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from psycopg2 import sql

from supercog.engine.tool_factory import ToolFactory, ToolCategory, ToolConfigError, LangChainCallback
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LangchainDocument
from supercog.shared.services import config
from firecrawl import FirecrawlApp
from io import BytesIO
from pypdf import PdfReader
import importlib
from collections import Counter
from uuid import UUID
import re
from openai import AsyncOpenAI
from supercog.engine.tools.basic_data import BasicDataTool
import time

@dataclass
class Document:
    content: str
    source: str
    line_number: int
    embedding: List[float] = field(default_factory=list)

@dataclass
class RAGTool(ToolFactory):
    embeddings: Optional[OpenAIEmbeddings] = None
    conn: Optional[psycopg2.extensions.connection] = None
    credentials: Dict[str, str] = field(default_factory=dict)
    firecrawl: Optional[FirecrawlApp] = None
    is_available: bool = False
    openai_client: Optional[AsyncOpenAI] = None

    def __init__(self):
        super().__init__(
            id="rag_tool",
            system_name="RAG Tool",
            help="""
Perform Retrieval-Augmented Generation tasks using pgvector for storage.
""",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/8/86/Database-icon.svg",
            auth_config = {
                "strategy_token": {
                    "embedding_index_name": "Database index name",
                },
            },
            category=ToolCategory.CATEGORY_GENAI
        )
        
        # Initialize credentials with a default value
        self.credentials = {"embedding_index_name": "default_embeddings"}
        
        # Check if embedding_index_name is provided in the credentials
        if self.run_context and self.run_context.credentials:
            provided_index_name = self.run_context.credentials.get("embedding_index_name")
            if provided_index_name:
                self.credentials["embedding_index_name"] = provided_index_name

        self.is_available = self._check_availability()

        if self.is_available:
            self.embeddings = OpenAIEmbeddings(openai_api_key=config.get_global("OPENAI_API_KEY"))
            self.conn = self._create_db_connection()
            if self.conn:
                self._setup_database()
            key = config.get_global("FIRECRAWL_API_KEY", required=False) or "abc123"
            self.firecrawl = FirecrawlApp(api_key=key)
            self.openai_client = AsyncOpenAI(api_key=config.get_global("OPENAI_API_KEY"))

    def _check_availability(self) -> bool:
        # Check if pgvector is installed
        try:
            importlib.import_module('pgvector')
        except ImportError:
            print("pgvector is not installed. RAGTool will not be available.")
            return False

        # Check if FIRECRAWL_API_KEY is set
        if not config.get_global("FIRECRAWL_API_KEY", required=False):
            print("FIRECRAWL_API_KEY is not set. RAGTool will not be available.")
            return False

        # Check if PGVECTOR_DB_URL is set
        if not os.environ.get('PGVECTOR_DB_URL'):
            print("PGVECTOR_DB_URL is not set. RAGTool will not be available.")
            return False

        return True

    def get_tools(self) -> List[Callable]:
        if not self.is_available:
            return []
        # Return a list of wrapped tool functions
        return self.wrap_tool_functions([
            self.add_to_index,
            self.add_single_webpage_to_index,
            self.add_website_to_index,
            self.search_index,
            self.hybrid_search,
            self.list_sources,
        ])

    async def keep_alive(self):
        """Send a keep-alive signal to prevent idle timeout."""
        if hasattr(self, 'run_context') and self.run_context:
            self.run_context.last_event = time.time()

    async def process_with_keep_alive(self, coroutine, interval=30):
        """
        Run a coroutine while periodically sending keep-alive signals.
        
        :param coroutine: The coroutine to run
        :param interval: Interval in seconds between keep-alive signals
        """
        keep_alive_task = asyncio.create_task(self._periodic_keep_alive(interval))
        try:
            return await coroutine
        finally:
            keep_alive_task.cancel()
            try:
                await keep_alive_task
            except asyncio.CancelledError:
                pass

    async def _periodic_keep_alive(self, interval):
        while True:
            await asyncio.sleep(interval)
            await self.keep_alive()

    async def add_to_index(self, source: str, file_format: str = "auto", skip_rows: int = 0, cleanup_col_names: bool = True) -> dict:
        """
        Add content to the index from various sources: local file, file URL, or dataframe-like content.
            
        :param source: Path to local file, URL, or content of a dataframe-like structure
        :param file_format: Format of the file or content ('auto', 'csv', 'excel', 'json', 'parquet', 'text', 'pdf', 'url')
        :param skip_rows: Number of rows to skip (for CSV and Excel files)
        :param cleanup_col_names: Whether to clean up column names (for dataframe-like content)
        :return: Dictionary with status and message
        """
        async def add_to_index_coroutine(source: str, file_format: str, skip_rows: int, cleanup_col_names: bool) -> dict:
            try:
                if not self.is_available:
                    return {"status": "error", "message": "RAGTool is not available. Check your configuration."}

                if self.conn is None:
                    return {"status": "error", "message": "Database connection is not established. Check your database configuration."}

                embedding_table_name = self._get_safe_table_name()
                if embedding_table_name.startswith('rag_public_'):
                    if self._is_table_indexed(embedding_table_name):
                        return {"status": "error", "message": "This public index has already been created and is read-only."}

                if file_format == "auto":
                    file_format = self._infer_format(source)

                if file_format == "url":
                    return await self._add_url_to_index(source)
                elif file_format in ["csv", "excel", "json", "parquet"]:
                    df = self._get_dataframe(source, file_format, skip_rows, cleanup_col_names)
                    documents = self._dataframe_to_documents(df, source)
                elif file_format in ["text", "pdf"]:
                    content = self._read_file(source)
                    documents = self._split_text(content, source)
                else:
                    return {"status": "error", "message": f"Unsupported file format: {file_format}"}

                result = await self._process_documents(documents, source)
                
                if embedding_table_name.startswith('rag_public_'):
                    self._revoke_write_permissions(embedding_table_name)

                return {"status": "success", "message": result}
            except Exception as e:
                return {"status": "error", "message": f"Error adding content to index: {str(e)}"}

        return await self.process_with_keep_alive(
            add_to_index_coroutine(source, file_format, skip_rows, cleanup_col_names)
        )

    def _infer_format(self, source: str) -> str:
        if source.startswith(('http://', 'https://')):
            return "url"
        else:
            return self._infer_format_from_name(source)

    async def _add_url_to_index(self, url: str) -> dict:
        try:
            content, mime_type = self._file_download(url)
            file_extension = mimetypes.guess_extension(mime_type)
            
            if file_extension in ['.csv', '.xlsx', '.xls', '.json', '.parquet']:
                df = self._content_to_dataframe(content, file_extension, url)
                documents = self._dataframe_to_documents(df, url)
            elif mime_type == 'application/pdf':
                text = self._read_pdf_from_bytes(content)
                documents = self._split_text(text, url)
            else:
                documents = self._split_text(content, url)
            
            result = await self._process_documents(documents, url)
            return {"status": "success", "message": result}
        except Exception as e:
            return {"status": "error", "message": f"Error adding URL content to index: {str(e)}"}

    def _split_text(self, content: Union[str, bytes], source: str) -> List[LangchainDocument]:
        if isinstance(content, bytes):
            text = self._bytes_to_text(content)
        else:
            text = content
        
        # Use RecursiveCharacterTextSplitter for improved chunking
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_text(text)
        
        return [LangchainDocument(page_content=chunk, metadata={"source": source}) for chunk in chunks]

    def _bytes_to_text(self, content: bytes) -> str:
        # Convert bytes to text, handling encoding issues
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError:
            detected_encoding = chardet.detect(content)['encoding']
            return content.decode(detected_encoding or 'utf-8', errors='replace')

    async def _process_documents(self, documents: List[LangchainDocument], source: str) -> str:
        # Process and store documents in the database
        self._setup_database()
        embedding_table_name = self._get_safe_table_name()
        total_docs = len(documents)
        with self.conn.cursor() as cur:
            for i, doc in enumerate(documents):
                await self.log(f"Adding doc {i + 1}/{total_docs} to index")
                clean_content = self._clean_text(doc.page_content)
                embedding = self.embeddings.embed_query(clean_content)
                cur.execute(sql.SQL("""
                INSERT INTO {} (content, source, line_number, embedding)
                VALUES (%s, %s, %s, %s::vector)
                """).format(sql.Identifier(embedding_table_name)), (clean_content, source, i, embedding))
        self.conn.commit()
        return f"Added {len(documents)} text chunks from {source} to the index."

    def _get_dataframe(self, data_source: str, file_format: str, skip_rows: int, cleanup_col_names: bool) -> pd.DataFrame:
        # Load data into a DataFrame based on the file format
        if file_format == "infer":
            file_format = self._infer_format_from_name(data_source)

        if file_format == "csv":
            df = pd.read_csv(data_source, skiprows=skip_rows)
        elif file_format == "parquet":
            df = pd.read_parquet(data_source)
        elif file_format == "json":
            # Read JSON file and handle different structures
            with open(data_source, 'r') as file:
                json_data = json.load(file)
            
            if isinstance(json_data, list):
                df = pd.DataFrame(json_data)
            elif isinstance(json_data, dict):
                # If it's a single object, wrap it in a list
                df = pd.DataFrame([json_data])
            else:
                # If it's neither a list nor a dict, create a single-row DataFrame
                df = pd.DataFrame([{"content": json.dumps(json_data)}])
        elif file_format in ["excel", "xlsx", "xls"]:
            df = pd.read_excel(data_source, skiprows=skip_rows)
        elif file_format == "text":
            with open(data_source, 'r') as file:
                content = file.read()
            df = pd.DataFrame([{"content": content}])
        else:
            raise ValueError(f"Unsupported file format: {file_format}")

        if cleanup_col_names:
            df.columns = (
                df.columns.str.strip().str.lower()
                .str.replace(r'\W+', '_', regex=True)
                .str.replace(r'_$', '', regex=True)
            )

        return df

    def _infer_format_from_name(self, file_name: str) -> str:
        # Infer the file format from the file name
        lower_name = file_name.lower()
        if lower_name.endswith(".csv"):
            return "csv"
        elif lower_name.endswith(".parquet"):
            return "parquet"
        elif lower_name.endswith((".xlsx", ".xls")):
            return "excel"
        elif lower_name.endswith(".json"):
            return "json"
        else:
            return "text"

    def _dataframe_to_documents(self, df: pd.DataFrame, source: str) -> List[LangchainDocument]:
        documents = []
        for index, row in df.iterrows():
            if len(df.columns) == 1 and 'content' in df.columns:
                content = row['content']
            else:
                content = json.dumps(row.to_dict())
            documents.append(LangchainDocument(page_content=content, metadata={"source": f"{source}:row{index}"}))
        return documents

    def search_index(self, query: str, num_results: int = 5) -> dict:
        """
        Searches for question context in the index, using semantic search. Returns matching documents and links.
        """
        try:
            self._setup_database()
            query_embedding = self.embeddings.embed_query(query)
            embedding_table_name = self._get_safe_table_name()
            
            with self.conn.cursor() as cur:
                cur.execute(sql.SQL("""
                SELECT content, source, line_number, embedding <=> %s::vector AS distance
                FROM {}
                ORDER BY distance
                LIMIT %s
                """).format(sql.Identifier(embedding_table_name)), (query_embedding, num_results))
                results = cur.fetchall()

            output = []
            for content, source, line_number, distance in results:
                filename = self._extract_filename(source)
                output.append({
                    "filename": filename,
                    "similarity": 1 - distance,
                    "chunk": content,
                    "reference": f"{source}"
                })

            return {"status": "success", "results": output}
        except ToolConfigError as e:
            raise e
        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "message": f"Error searching index: {str(e)}"}

    def _extract_filename(self, source: str) -> str:
        """
        Extract filename from source, handling both file paths and URLs.
        """
        if source.startswith(('http://', 'https://')):
            # For URLs, use the last part of the path or the domain if no path
            parsed_url = urlparse(source)
            path = parsed_url.path.strip('/')
            return path.split('/')[-1] if path else parsed_url.netloc
        else:
            # For file paths, use os.path.basename
            return os.path.basename(source)

    def _read_file(self, file_name: str) -> str:
        # Read file content based on file extension
        file_extension = os.path.splitext(file_name)[1].lower()
        
        if file_extension in ['.xlsx', '.xls']:
            df = pd.read_excel(file_name, engine='openpyxl')
            return df.to_json()
        elif file_extension == '.pdf':
            return self._read_pdf(file_name)
        elif file_extension == '.json':
            return self._read_json(file_name)
        elif file_extension in ['.txt', '.md', '.csv', '.xml', '.html', '.htm', '.log', '.ini', '.cfg', '.yaml', '.yml']:
            return self._read_text_file(file_name)
        else:
            return self._read_unknown_file(file_name)

    def _read_text_file(self, file_name: str) -> str:
        # Read content of text-based files
        file_extension = os.path.splitext(file_name)[1].lower()
        with open(file_name, 'r', encoding='utf-8', errors='replace') as f:
            if file_extension == '.csv':
                csv_reader = csv.reader(f)
                return '\n'.join([','.join(row) for row in csv_reader])
            elif file_extension in ['.html', '.htm']:
                return html2text.html2text(f.read())
            else:
                return f.read()

    def _read_unknown_file(self, file_name: str) -> str:
        # Read content of unknown file types
        with open(file_name, 'rb') as f:
            raw_content = f.read()
        result = chardet.detect(raw_content)
        encoding = result['encoding'] or 'utf-8'
        return self._clean_text(raw_content.decode(encoding, errors='replace'))

    def _read_pdf(self, file_name: str) -> str:
        # Read content of PDF files using LangChain's PyPDFLoader
        loader = PyPDFLoader(file_name)
        pages = loader.load_and_split()
        text = "\n".join([page.page_content for page in pages])
        return self._clean_text(text)

    def _read_json(self, file_name: str) -> str:
        # Read content of JSON files
        with open(file_name, 'rb') as f:
            raw_content = f.read()
        result = chardet.detect(raw_content)
        encoding = result['encoding'] or 'utf-8'
        content = raw_content.decode(encoding, errors='replace')
        return json.dumps(json.loads(content))

    def _file_download(self, url: str) -> Tuple[bytes, str]:
        # Download file content from a URL
        r = requests.get(url)
        if r.status_code == 200:
            mime_type = r.headers.get('content-type', '').lower()
            return r.content, mime_type
        else:
            raise Exception(f"Error: {r.status_code} {r.reason}")

    def _content_to_dataframe(self, content: bytes, file_extension: str, url: str) -> pd.DataFrame:
        # Convert file content to DataFrame based on file extension
        if file_extension == '.csv':
            return pd.read_csv(BytesIO(content))
        elif file_extension in ['.xlsx', '.xls']:
            return pd.read_excel(BytesIO(content))
        elif file_extension == '.json':
            return pd.read_json(BytesIO(content))
        elif file_extension == '.parquet':
            return pd.read_parquet(BytesIO(content))
        else:
            raise ValueError(f"Unsupported file format for URL: {url}")

    def _clean_text(self, text: str) -> str:
        # Clean text by removing non-printable characters and extra whitespace
        text = ''.join(char for char in text if char.isprintable() or char in ['\n', '\t'])
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _read_pdf_from_bytes(self, content: bytes) -> str:
        try:
            # Use BytesIO to create an in-memory file-like object
            pdf_file = BytesIO(content)
            
            # Use PdfReader to read the PDF content
            pdf_reader = PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            return self._clean_text(text)
        except Exception as e:
            raise Exception(f"Error reading PDF content: {str(e)}")

    async def add_single_webpage_to_index(self, url: str) -> dict:
        """
        Add content to the index from Single Webpage.
        """
        try:
            embedding_table_name = self._get_safe_table_name()
            
            # Ensure the table exists before checking if it's indexed
            self._setup_database()
            
            if embedding_table_name.startswith('rag_public_'):
                if self._is_table_indexed(embedding_table_name):
                    return {"status": "error", "message": "This public index has already been created and is read-only."}

            await self.log(f"Scraping url: {url}")
            scrape_result = self.firecrawl.scrape_url(url, params={
                'formats': ['markdown']
            })
            await self.log(f"Scrape is done")
            
            # Check if scrape_result is a dictionary and has a 'markdown' key
            if isinstance(scrape_result, dict) and 'markdown' in scrape_result:
                content = scrape_result['markdown']
            else:
                # If the structure is different, try to extract content or return an error
                return {"status": "error", "message": f"Unexpected response structure from Firecrawl for URL: {url}"}
            
            if not content.strip():
                return {"status": "error", "message": f"No content found on the page: {url}"}

            documents = self._split_text(content, url)
            await self.log(f"Processing page into {len(documents)} chunks")
            result = await self._process_documents(documents, url)

            if embedding_table_name.startswith('rag_public_'):
                self._revoke_write_permissions(embedding_table_name)
            
            result_message = f"Added content from {url} to the index."
            return {"status": "success", "message": result_message}
        except Exception as e:
            return {"status": "error", "message": f"Error adding webpage to index: {str(e)}"}

    async def add_website_to_index(self, url: str, max_pages: int = 50) -> dict:
        """
        Add content to the index from Website and its subpages.
        
        :param url: The starting URL to crawl
        :param max_pages: Maximum number of pages to crawl (default: 50)
        :return: Dictionary with status and message
        """
        async def add_website_to_index_coroutine():
            try:
                if not self.is_available:
                    return {"status": "error", "message": "RAGTool is not available. Check your configuration."}

                if self.conn is None:
                    return {"status": "error", "message": "Database connection is not established. Check your database configuration."}

                embedding_table_name = self._get_safe_table_name()
                if embedding_table_name.startswith('rag_public_'):
                    if self._is_table_indexed(embedding_table_name):
                        return {"status": "error", "message": "This public index has already been created and is read-only."}

                # Use Firecrawl to crawl the website
                await self.log(f"Crawling site: {url}")
                crawl_response = self.firecrawl.crawl_url(
                    url,
                    params={
                        'limit': max_pages,
                        'scrapeOptions': {
                            'formats': ['markdown']
                        }
                    }
                )

                if not crawl_response or not isinstance(crawl_response, dict):
                    return {"status": "error", "message": f"Unexpected response from Firecrawl for URL: {url}"}

                # Check if the crawl was successful
                if crawl_response.get('status') != 'completed':
                    return {"status": "error", "message": f"Crawl not completed. Status: {crawl_response.get('status')}"}

                # Get the crawled data
                crawl_data = crawl_response.get('data', [])
                if not crawl_data:
                    return {"status": "error", "message": f"No content found on the website: {url}"}

                total_pages = len(crawl_data)
                await self.log(f"Found {total_pages} pages")
                processed_pages = 0

                for index, page in enumerate(crawl_data):
                    if isinstance(page, dict) and 'markdown' in page and page['markdown'].strip():
                        content = page['markdown']
                        page_url = page.get('metadata', {}).get('sourceURL', url)
                        await self.log(f"Adding {url} to index ({index + 1}/{total_pages})")
                        documents = self._split_text(content, page_url)
                        await self._process_documents(documents, page_url)
                        processed_pages += 1
                        await asyncio.sleep(0.2)  # Add a small delay to avoid rate limiting
                    else:
                        print(f"Skipping page with no content: {page.get('metadata', {}).get('sourceURL', 'Unknown URL')}")

                if embedding_table_name.startswith('rag_public_'):
                    self._revoke_write_permissions(embedding_table_name)

                result_message = f"Added content from {processed_pages} pages out of {total_pages} crawled from {url} to the index."
                return {"status": "success", "message": result_message}
            except Exception as e:
                return {"status": "error", "message": f"Error adding website to index: {str(e)}"}

        return await self.process_with_keep_alive(add_website_to_index_coroutine())

    def _create_db_connection(self):
        try:
            # Create a database connection using the PGVECTOR_DB_URL environment variable
            database_url = os.environ.get('PGVECTOR_DB_URL')
            if not database_url:
                print("PGVECTOR_DB_URL environment variable is not set")
                return None
            conn = psycopg2.connect(database_url)
            register_vector(conn)
            return conn
        except Exception as e:
            print(f"Error creating database connection: {str(e)}")
            return None

    def _get_tenant_id(self) -> str:
        if hasattr(self, 'run_context') and self.run_context:
            tenant_id = getattr(self.run_context, 'tenant_id', None)
            if tenant_id:
                return str(tenant_id)
        return 'default'  # Fallback to a default value if tenant_id is not available

    def _get_safe_table_name(self) -> str:
        # Get the tenant_id using the new method
        tenant_id = self._get_tenant_id()
        
        # Sanitize the tenant_id
        sanitized_id = re.sub(r'[^a-zA-Z0-9]', '', tenant_id)
        
        # Get the embedding_index_name (category of context)
        category = self.credentials.get('embedding_index_name', 'default')
        
        # Sanitize the category name
        safe_category = re.sub(r'[^a-zA-Z0-9_]', '_', category.lower())
        
        # Construct the table name
        if safe_category.startswith('public_'):
            table_name = f"rag_{safe_category}"
        else:
            table_name = f"rag_{safe_category}_{sanitized_id}"
        
        # Ensure the table name is valid for PostgreSQL
        table_name = re.sub(r'[^a-zA-Z0-9_]', '_', table_name)
        
        # Truncate if necessary (PostgreSQL has a 63-character limit for identifiers)
        return table_name[:63]

    def _setup_database(self):
        if not self.conn:
            raise ToolConfigError("Database connection not available. Skipping database setup.")
        try:
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

                embedding_table_name = self._get_safe_table_name()
                
                # Check if the table already exists
                cur.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                )
                """, (embedding_table_name,))
                table_exists = cur.fetchone()[0]

                if not table_exists:
                    cur.execute(f"""
                    CREATE TABLE {embedding_table_name} (
                        id SERIAL PRIMARY KEY,
                        content TEXT,
                        source TEXT,
                        line_number INTEGER,
                        embedding vector(1536)
                    )
                    """)
                    cur.execute(f"CREATE INDEX {embedding_table_name}_embedding_idx ON {embedding_table_name} USING ivfflat (embedding vector_l2_ops)")
                    print(f"Created new table: {embedding_table_name}")
                else:
                    print(f"Table {embedding_table_name} already exists")

            self.conn.commit()
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            raise ToolConfigError(f"Error setting up database: {str(e)}")

    def _is_table_indexed(self, table_name: str) -> bool:
        """Check if the table exists and has any rows."""
        try:
            with self.conn.cursor() as cur:
                # First, check if the table exists
                cur.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_name = %s
                )
                """, (table_name,))
                table_exists = cur.fetchone()[0]
                
                if not table_exists:
                    return False  # Table doesn't exist, so it's not indexed
                
                # If the table exists, check if it has any rows
                cur.execute(sql.SQL("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM {} 
                    LIMIT 1
                )
                """).format(sql.Identifier(table_name)))
                has_rows = cur.fetchone()[0]
                
                return has_rows
        except Exception as e:
            print(f"Error checking if table is indexed: {str(e)}")
            return False

    def _revoke_write_permissions(self, table_name: str):
        """Revoke write permissions for the given table."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON {table_name} FROM PUBLIC;
                REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON {table_name} FROM current_user;
                """)
            self.conn.commit()
            print(f"Revoked write permissions for public table: {table_name}")
        except Exception as e:
            print(f"Error revoking write permissions: {str(e)}")
            self.conn.rollback()

    def list_sources(self) -> dict:
        """
        List all unique sources (files) stored in the index with their chunk counts.
        Returns a dictionary with status and the formatted content of the sources list.
        """
        try:
            self._setup_database()
            embedding_table_name = self._get_safe_table_name()
            
            with self.conn.cursor() as cur:
                # Get sources and their chunk counts
                cur.execute(sql.SQL("""
                SELECT source, COUNT(*) as chunk_count
                FROM {}
                GROUP BY source
                ORDER BY chunk_count DESC
                """).format(sql.Identifier(embedding_table_name)))
                sources = cur.fetchall()

            # Prepare the output
            output_lines = []
            for source, chunk_count in sources:
                # Create a clickable link
                clickable_link = f"[{source}]({source})"
                output_lines.append(f"{clickable_link}, {chunk_count} chunks")

            # Join the lines with newlines
            formatted_output = "\n".join(output_lines)

            return {"status": "success", "content": formatted_output}

        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "message": f"Error listing sources: {str(e)}"}

    async def hybrid_search(self, query: str, num_results: int = 5) -> dict:
        """
        Performs a hybrid search combining semantic and keyword search, with re-ranking.
        """
        try:
            self._setup_database()
            
            # Perform semantic search using existing search_index method
            semantic_results = self.search_index(query, num_results)
            if semantic_results["status"] != "success":
                return semantic_results  # Return error if semantic search fails
            
            semantic_results = [
                (item["chunk"], item["reference"], 0, item["similarity"])  # line_number is set to 0 as it's not provided by search_index
                for item in semantic_results["results"]
            ]
            
            # Perform keyword search
            keyword_results = await self._keyword_search(query, num_results)
            
            # Combine and deduplicate results
            combined_results = list(set(semantic_results + keyword_results))
            
            # Re-rank results
            reranked_results = await self._rerank(query, combined_results)
            
            output = []
            for content, source, _, score in reranked_results[:num_results]:
                filename = self._extract_filename(source)
                output.append({
                    "filename": filename,
                    "similarity": score,
                    "chunk": content,
                    "reference": f"{source}"
                })

            return {"status": "success", "results": output}
        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "message": f"Error performing hybrid search: {str(e)}"}

    async def _keyword_search(self, query: str, num_results: int) -> List[Tuple[str, str, int, float]]:
        embedding_table_name = self._get_safe_table_name()
        
        with self.conn.cursor() as cur:
            cur.execute(sql.SQL("""
            SELECT content, source, line_number, ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', %s)) AS rank
            FROM {}
            WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s
            """).format(sql.Identifier(embedding_table_name)), (query, query, num_results))
            return cur.fetchall()

    async def _rerank(self, query: str, results: List[Tuple[str, str, int, float]]) -> List[Tuple[str, str, int, float]]:
        """
        Re-rank the results using OpenAI's API.
        """
        try:
            # Prepare the input for OpenAI API
            inputs = [
                {"query": query, "text": result[0]}
                for result in results
            ]

            # Call OpenAI API to get relevance scores
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that ranks the relevance of text chunks to a given query."},
                    {"role": "user", "content": f"Rank the relevance of the following text chunks to the query '{query}':\n\n" + "\n\n".join([f"{i+1}. {input['text']}" for i, input in enumerate(inputs)])},
                ],
                functions=[
                    {
                        "name": "rank_relevance",
                        "description": "Rank the relevance of text chunks to a given query",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "scores": {
                                    "type": "array",
                                    "items": {
                                        "type": "number"
                                    },
                                    "description": "The relevance scores for each text chunk, in the same order as the input",
                                },
                            },
                            "required": ["scores"],
                        },
                    }
                ],
                function_call={"name": "rank_relevance"},
            )

            # Extract the relevance scores from the API response
            scores = json.loads(response.choices[0].message.function_call.arguments)["scores"]

            # Re-rank the results based on the scores
            reranked_results = sorted(results, key=lambda x: scores[results.index(x)], reverse=True)

            return reranked_results
        except Exception as e:
            print(f"Error re-ranking results: {str(e)}")
            return results

    def __del__(self):
        if self.is_available and hasattr(self, 'conn') and self.conn:
            self.conn.close()