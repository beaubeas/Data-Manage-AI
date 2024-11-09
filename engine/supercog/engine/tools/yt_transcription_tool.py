from typing import Callable, List, Dict, Optional, Union
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs
import yt_dlp
import importlib

from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.services import config
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LangchainDocument

from openai import OpenAI
import psycopg2
from psycopg2 import sql
from pgvector.psycopg2 import register_vector

@dataclass
class YouTubeTranscriptionTool(ToolFactory):
    embeddings: Optional[OpenAIEmbeddings] = None
    conn: Optional[psycopg2.extensions.connection] = None
    credentials: Dict[str, str] = field(default_factory=dict)
    openai_client: Optional[OpenAI] = None
    ydl_opts: Dict[str, Union[str, List[Dict[str, str]]]] = field(default_factory=dict)
    embedding_table_name: str = "youtube_transcriptions"
    is_available: bool = False

    def __init__(self):
        super().__init__(
            id="youtube_transcription_tool",
            system_name="YouTube Transcription",
            help="""
Transcribe YouTube videos and add them to the RAG database.
""",
            logo_url="https://www.youtube.com/favicon.ico",
            auth_config = {
                "strategy_token": {
                    "embedding_index_name": "Database index name",
                },
            },
            category=ToolCategory.CATEGORY_SPEECH
        )
        
        self.is_available = self._check_availability()
        
        if self.is_available:
            self.embedding_table_name = self.credentials.get('embedding_index_name', 'youtube_transcriptions')
            self.openai_client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))
            self.embeddings = OpenAIEmbeddings(openai_api_key=self.openai_client.api_key)
            
            self.conn = self._create_db_connection()
            if self.conn:
                self._setup_database()
            
            self.ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': '%(id)s.%(ext)s',
            }

    def _check_availability(self) -> bool:
        # Check if pgvector is installed
        try:
            importlib.import_module('pgvector')
        except ImportError:
            print("pgvector is not installed. YouTubeTranscriptionTool will not be available.")
            return False

        # Check if DATABASE_URL is set
        if not os.environ.get('DATABASE_URL'):
            print("DATABASE_URL is not set. YouTubeTranscriptionTool will not be available.")
            return False

        return True

    def _create_db_connection(self):
        try:
            database_url = os.environ.get('DATABASE_URL')
            if not database_url:
                print("DATABASE_URL environment variable is not set")
                return None
            conn = psycopg2.connect(database_url)
            register_vector(conn)
            return conn
        except Exception as e:
            print(f"Error creating database connection: {str(e)}")
            return None

    def _setup_database(self):
        if not self.conn:
            print("Database connection not available. Skipping database setup.")
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    id SERIAL PRIMARY KEY,
                    video_id TEXT UNIQUE,
                    title TEXT,
                    url TEXT,
                    content TEXT,
                    embedding vector(1536)
                )
                """).format(sql.Identifier(self.embedding_table_name)))
                cur.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING ivfflat (embedding vector_l2_ops)").format(
                    sql.Identifier(f"{self.embedding_table_name}_embedding_idx"),
                    sql.Identifier(self.embedding_table_name)
                ))
            self.conn.commit()
        except Exception as e:
            print(f"Error setting up database: {str(e)}")
            self.conn.rollback()

    def get_tools(self) -> List[Callable]:
        if not self.is_available:
            return []
        return self.wrap_tool_functions([
            self.transcribe_youtube_video,
            self.search_transcriptions,
        ])

    def transcribe_youtube_video(self, youtube_url: str) -> dict:
        """
        Add content to the memory from YouTube Videos.
        """
        try:
            video_id = self._extract_video_id(youtube_url)
            audio_file_path = self._download_audio(youtube_url)
            transcription = self._transcribe_audio(audio_file_path)
            title = self._get_video_title(youtube_url)  # New method to get video title
            documents = self._split_transcription(transcription, video_id, title)
            result = self._process_documents(documents, youtube_url, video_id)
            os.remove(audio_file_path)  # Clean up temporary audio file
            return {"status": "success", "message": result}
        except Exception as e:
            return {"status": "error", "message": f"Error transcribing YouTube video: {str(e)}"}

    def _extract_video_id(self, youtube_url: str) -> str:
        parsed_url = urlparse(youtube_url)
        if parsed_url.hostname == 'youtu.be':
            return parsed_url.path[1:]
        if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed_url.path == '/watch':
                return parse_qs(parsed_url.query)['v'][0]
            if parsed_url.path[:7] == '/embed/':
                return parsed_url.path.split('/')[2]
            if parsed_url.path[:3] == '/v/':
                return parsed_url.path.split('/')[2]
        raise ValueError('Invalid YouTube URL')

    def _download_audio(self, youtube_url: str) -> str:
        temp_dir = os.path.join(os.getcwd(), 'temp_audio')
        os.makedirs(temp_dir, exist_ok=True)
        
        self.ydl_opts['outtmpl'] = os.path.join(temp_dir, '%(id)s.%(ext)s')

        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            filename = ydl.prepare_filename(info)
            final_filename = os.path.splitext(filename)[0] + '.mp3'
        
        os.chmod(final_filename, 0o777)
        return final_filename

    def _transcribe_audio(self, audio_file_path: str) -> Dict[str, Union[str, List[Dict[str, Union[float, str]]]]]:
        with open(audio_file_path, 'rb') as audio_file:
            response = self.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en"
            )
        
        return {
            "text": response.text,
            "segments": [{"start": 0}]
        }

    def _split_transcription(self, transcription: Dict[str, Union[str, List[Dict[str, Union[float, str]]]]], video_id: str, title: str) -> List[LangchainDocument]:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_text(transcription["text"])
        
        documents = []
        for i, chunk in enumerate(chunks):
            start_time = transcription["segments"][i]["start"] if i < len(transcription["segments"]) else 0
            documents.append(LangchainDocument(
                page_content=chunk,
                metadata={"video_id": video_id, "title": title, "line_number": i, "timestamp": start_time}
            ))
        return documents

    def _process_documents(self, documents: List[LangchainDocument], source: str, video_id: str) -> str:
        with self.conn.cursor() as cur:
            for doc in documents:
                embedding = self.embeddings.embed_query(doc.page_content)
                cur.execute(sql.SQL("""
                INSERT INTO {} (video_id, title, url, content, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (video_id) DO UPDATE SET
                content = EXCLUDED.content || E'\n' || {}.content,
                embedding = EXCLUDED.embedding
                """).format(sql.Identifier(self.embedding_table_name), sql.Identifier(self.embedding_table_name)), (
                    video_id,
                    doc.metadata.get("title", ""),
                    source,
                    doc.page_content,
                    embedding
                ))
        self.conn.commit()
        return f"Added transcription for video {video_id} to the index."

    def search_transcriptions(self, query: str, num_results: int = 5) -> dict:
        """
        Search content from memory.
        """
        try:
            query_embedding = self.embeddings.embed_query(query)
            
            with self.conn.cursor() as cur:
                cur.execute(sql.SQL("""
                SELECT video_id, title, url, content, embedding <=> %s::vector AS distance
                FROM {}
                ORDER BY distance
                LIMIT %s
                """).format(sql.Identifier(self.embedding_table_name)), (query_embedding, num_results))
                results = cur.fetchall()

            output = []
            for video_id, title, url, content, distance in results:
                output.append({
                    "video_id": video_id,
                    "title": title,
                    "similarity": 1 - distance,
                    "chunk": content,
                    "youtube_link": url
                })

            return {"status": "success", "results": output}
        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "message": f"Error searching transcriptions: {str(e)}"}

    def _get_video_title(self, youtube_url: str) -> str:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            return info.get('title', '')

    def __del__(self):
        try:
            if self.is_available and hasattr(self, 'conn') and self.conn is not None:
                self.conn.close()
            
            temp_dir = os.path.join(os.getcwd(), 'temp_audio')
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, file)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        print(f"Error deleting {file_path}: {e}")
                os.rmdir(temp_dir)
        except:
            pass