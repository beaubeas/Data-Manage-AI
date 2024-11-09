import io
import tempfile
import os
from typing import Callable, List, Optional, Tuple, Dict
from PyPDF2 import PdfReader, PdfWriter
from fpdf import FPDF
from urllib.parse import urlparse
import markdown2
from supercog.engine.tool_factory import ToolFactory, ToolCategory, LLMFullResult
from supercog.shared.services import config
from supercog.engine.tools.s3_utils import get_boto_client, calc_s3_url, public_image_bucket
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
import re
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pydantic import Field
import json
from openai import AsyncOpenAI
import fitz
from PIL import Image
import pandas as pd
import base64
from supercog.engine.filesystem import unrestricted_filesystem
from supercog.shared.utils import upload_file_to_s3
import uuid

class PDFTool(ToolFactory):
    conn: Optional[psycopg2.extensions.connection] = Field(default=None)
    embeddings: Optional[OpenAIEmbeddings] = Field(default=None)
    openai_client: Optional[AsyncOpenAI] = Field(default=None)

    def __init__(self, **data):
        super().__init__(
            id="pdf_tool",
            system_name="PDF Tool",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/PDF_file_icon.svg/534px-PDF_file_icon.svg.png",
            auth_config={},
            category=ToolCategory.CATEGORY_FILES,
            help="""
Interact with PDF files: read, write content, index PDFs, and perform hybrid search.
""",
            **data
        )
        self.conn = self._create_db_connection()
        self.embeddings = OpenAIEmbeddings(openai_api_key=config.get_global("OPENAI_API_KEY"))
        self.openai_client = AsyncOpenAI(api_key=config.get_global("OPENAI_API_KEY"))

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            #self.read_pdf_into_index,
            self.read_pdf,
            self.save_pdf_file,
#            self.hybrid_search,
            self.convert_pdf_to_images,
        ])

    def read_pdf(self, file_name: str) -> str:
        """
        Reads a PDF file and extracts text from all pages.

        Args:
            file_name (str): The name of the PDF file in S3.

        Returns:
            str: The extracted text from all pages of the PDF.
        """
        try:
            tenant_id = self.run_context.tenant_id
            folder_name = self.run_context.user_id
            s3_client = get_boto_client('s3')
            bucket_name = config.get_global("S3_FILES_BUCKET_NAME")
            object_name = f"{tenant_id}/{folder_name}/{file_name}"

            response = s3_client.get_object(Bucket=bucket_name, Key=object_name)
            pdf_content = response['Body'].read()

            pdf_reader = PdfReader(io.BytesIO(pdf_content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            download_url: dict = self.run_context.get_file_url(file_name)
            result = f"PDF Content (Download link: {download_url.get('url', '')})\n\n{text}"
            return LLMFullResult(result)
        except Exception as e:
            return f"Error reading PDF: {str(e)}"

    # def read_pdf_into_index(self, file_name: str) -> str:
    #     """
    #     Reads a PDF file, extracts text from all pages, and indexes the content.

    #     Args:
    #         file_name (str): The name of the PDF file in S3.

    #     Returns:
    #         str: The extracted text from all pages of the PDF and indexing result.
    #     """
    #     try:
    #         tenant_id = self.run_context.tenant_id
    #         folder_name = self.run_context.user_id
    #         s3_client = get_boto_client('s3')
    #         bucket_name = config.get_global("S3_FILES_BUCKET_NAME")
    #         object_name = f"{tenant_id}/{folder_name}/{file_name}"

    #         response = s3_client.get_object(Bucket=bucket_name, Key=object_name)
    #         pdf_content = response['Body'].read()

    #         pdf_reader = PdfReader(io.BytesIO(pdf_content))
    #         text = ""
    #         for page in pdf_reader.pages:
    #             text += page.extract_text() + "\n"
            
    #         download_url: dict = self.run_context.get_file_url(file_name)
            
    #         # Index the PDF content
    #         indexing_result = self._index_pdf_content(text, file_name)
            
    #         result = f"PDF Content (Download link: {download_url.get('url', '')})\n\n{text}\n\n{indexing_result}"
    #         return LLMFullResult(result)
    #     except Exception as e:
    #         return f"Error reading and indexing PDF: {str(e)}"

    # def _index_pdf_content(self, text: str, file_name: str) -> str:
    #     try:
    #         # Split the text into chunks
    #         text_splitter = RecursiveCharacterTextSplitter(
    #             chunk_size=1000,
    #             chunk_overlap=200,
    #             length_function=len,
    #             separators=["\n\n", "\n", " ", ""]
    #         )
    #         chunks = text_splitter.split_text(text)

    #         # Index the chunks
    #         self._setup_database()
    #         embedding_table_name = self._get_safe_table_name(self.run_context.tenant_id)

    #         with self.conn.cursor() as cur:
    #             for i, chunk in enumerate(chunks):
    #                 embedding = self.embeddings.embed_query(chunk)
    #                 cur.execute(sql.SQL("""
    #                 INSERT INTO {} (content, source, page_number, embedding)
    #                 VALUES (%s, %s, %s, %s::vector)
    #                 """).format(sql.Identifier(embedding_table_name)), (chunk, file_name, i, embedding))

    #         self.conn.commit()

    #         return f"Successfully indexed {len(chunks)} chunks from {file_name}"
    #     except Exception as e:
    #         if self.conn:
    #             self.conn.rollback()
    #         return f"Error indexing PDF content: {str(e)}"

    def save_pdf_file(self, content: str, filename: str = None, source_format: str="markdown"):
        """ 
        Saves the given text as a PDF file, uploads it to S3, and indexes the content.

        Args:
            filename (str): The name of the file to be saved in S3.
            content (str): The content to be written to the PDF.
            source_format (str): The format of the content ('markdown' or 'text').

        Returns:
            str: A message indicating the result of the operation.
        """
        try:
            link = """\n\n_Created by_ [Supercog](https://supercog.ai)\n"""

            html = markdown2.markdown(content + link) # if source_format == "markdown" else content

            if filename is None:
                filename = f"generated_pdf_{self.run_context.run_id}.pdf"
            elif not filename.lower().endswith('.pdf'):
                filename += '.pdf'

            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.write_html(html)
            pdf.output(filename)

            self.run_context.upload_user_file_to_s3(
                file_name=filename,
                mime_type="application/pdf"
            )
            download_url: dict = self.run_context.get_file_url(filename)

            # Extract text from the generated PDF
            with open(filename, 'rb') as file:
                pdf_reader = PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"

            result = f"PDF file saved, download link: {download_url.get('url', '')}"
            return result
        except Exception as e:
            return f"Error saving and indexing PDF file: {str(e)}"

    def _create_db_connection(self):
        try:
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

    def _get_safe_table_name(self, tenant_id: str) -> str:
        sanitized_id = re.sub(r'[^a-zA-Z0-9]', '', tenant_id)
        table_name = f"{sanitized_id}_pdfs"
        return table_name[:63]  # PostgreSQL has a 63-character limit for identifiers

    def _setup_database(self):
        if not self.conn:
            raise Exception("Database connection not available. Skipping database setup.")
        try:
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

                embedding_table_name = self._get_safe_table_name(self.run_context.tenant_id)
                
                cur.execute(sql.SQL("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = {}
                )
                """).format(sql.Literal(embedding_table_name)))
                table_exists = cur.fetchone()[0]

                if not table_exists:
                    cur.execute(sql.SQL("""
                    CREATE TABLE {} (
                        id SERIAL PRIMARY KEY,
                        content TEXT,
                        source TEXT,
                        page_number INTEGER,
                        embedding vector(1536)
                    )
                    """).format(sql.Identifier(embedding_table_name)))
                    
                    # Create the index with a properly formatted name
                    index_name = f"{embedding_table_name}_embedding_idx"
                    cur.execute(sql.SQL("CREATE INDEX {} ON {} USING ivfflat (embedding vector_l2_ops)").format(
                        sql.Identifier(index_name),
                        sql.Identifier(embedding_table_name)
                    ))
                    print(f"Created new table and index: {embedding_table_name}")
                else:
                    print(f"Table {embedding_table_name} already exists")

            self.conn.commit()
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Error setting up database: {str(e)}")

    # async def hybrid_search(self, query: str, num_results: int = 5) -> dict:
    #     """
    #     Performs a hybrid search combining semantic and keyword search, with re-ranking.
    #     """
    #     try:
    #         self._setup_database()
            
    #         # Perform semantic search
    #         semantic_results = self._semantic_search(query, num_results)
            
    #         # Perform keyword search
    #         keyword_results = await self._keyword_search(query, num_results)
            
    #         # Combine and deduplicate results
    #         combined_results = list(set(semantic_results + keyword_results))
            
    #         # Re-rank results
    #         reranked_results = await self._rerank(query, combined_results)
            
    #         output = []
    #         for content, source, _, score in reranked_results[:num_results]:
    #             filename = self._extract_filename(source)
    #             output.append({
    #                 "filename": filename,
    #                 "similarity": score,
    #                 "chunk": content,
    #                 "reference": f"{source}"
    #             })

    #         return {"status": "success", "results": output}
    #     except Exception as e:
    #         self.conn.rollback()
    #         return {"status": "error", "message": f"Error performing hybrid search: {str(e)}"}

    def _semantic_search(self, query: str, num_results: int) -> List[Tuple[str, str, int, float]]:
        query_embedding = self.embeddings.embed_query(query)
        embedding_table_name = self._get_safe_table_name(self.run_context.tenant_id)
        
        with self.conn.cursor() as cur:
            cur.execute(sql.SQL("""
            SELECT content, source, page_number, embedding <=> %s::vector AS distance
            FROM {}
            ORDER BY distance
            LIMIT %s
            """).format(sql.Identifier(embedding_table_name)), (query_embedding, num_results))
            results = cur.fetchall()

        return [(content, source, page_number, 1 - distance) for content, source, page_number, distance in results]

    async def _keyword_search(self, query: str, num_results: int) -> List[Tuple[str, str, int, float]]:
        embedding_table_name = self._get_safe_table_name(self.run_context.tenant_id)
        
        with self.conn.cursor() as cur:
            cur.execute(sql.SQL("""
            SELECT content, source, page_number, ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', %s)) AS rank
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

            scores = json.loads(response.choices[0].message.function_call.arguments)["scores"]

            # Re-rank the results based on the scores
            reranked_results = sorted(results, key=lambda x: scores[results.index(x)], reverse=True)

            return reranked_results
        except Exception as e:
            print(f"Error re-ranking results: {str(e)}")
            return results

    def _extract_filename(self, source: str) -> str:
        """
        Extract filename from source, handling both file paths and URLs.
        """
        if source.startswith(('http://', 'https://')):
            parsed_url = urlparse(source)
            path = parsed_url.path.strip('/')
            return path.split('/')[-1] if path else parsed_url.netloc
        else:
            return os.path.basename(source)

    def convert_pdf_to_images(self, file_name: str) -> dict:
        """
        Converts a PDF file to a set of images (one per page), uploads them to S3,
        and returns their S3 links in a dictionary.

        Args:
            file_name (str): The name of the PDF file in S3.

        Returns:
            dict: A dictionary containing the S3 links of the images.
        """
        try:
            tenant_id = self.run_context.tenant_id
            folder_name = self.run_context.user_id
            s3_client = get_boto_client('s3')
            bucket_name = config.get_global("S3_FILES_BUCKET_NAME")
            object_name = f"{tenant_id}/{folder_name}/{file_name}"

            response = s3_client.get_object(Bucket=bucket_name, Key=object_name)
            pdf_content = response['Body'].read()

            # Open the PDF file
            pdf_document = fitz.open(stream=pdf_content, filetype="pdf")
            images_data = []

            # Get the base name of the PDF file (without extension)
            pdf_base_name = os.path.splitext(file_name)[0]

            with unrestricted_filesystem():
                for page_num in range(len(pdf_document)):
                    # Get the page
                    page = pdf_document[page_num]
                    
                    # Convert page to image
                    pix = page.get_pixmap()
                    
                    # Convert pixmap to PIL Image
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    
                    # Create a meaningful filename for the image
                    image_filename = f"{pdf_base_name}_page_{page_num + 1}.png"
                    img.save(image_filename, format='PNG')
                    
                    # Upload image to S3 with the new filename
                    self.run_context.upload_user_file_to_s3(
                        file_name=image_filename,
                        mime_type="image/png"
                    )

                    download_url: dict = self.run_context.get_file_url(image_filename)

                    s3_link = download_url.get('url', '')

                    images_data.append({
                        'page_number': page_num + 1,
                        'image_url': s3_link
                    })

                    # Remove the temporary file
                    os.remove(image_filename)

            # Close the PDF document
            pdf_document.close()

            return {
                "status": "success",
                "message": f"Successfully converted {len(images_data)} pages to images",
                "images": images_data
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error converting PDF to images and uploading to S3: {str(e)}"
            }

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()