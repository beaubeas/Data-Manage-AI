from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.logging import logger
from supercog.shared.services import db_connect
from sqlmodel import Session, select
from typing import Callable, Optional
import uuid
from datetime import datetime

from supercog.engine.db import CompressedHistoryMessage

engine = db_connect("engine")

MEMORY_COMPRESSION_TOOL_ID = "memory_compression_tool_id"

class MemoryCompressionTool(ToolFactory):
    
    def __init__(self):
        super().__init__(
            id=MEMORY_COMPRESSION_TOOL_ID,
            system_name="Memory Compression",
            logo_url="https://i.imgur.com/hhEXJl1.png",
            help="""
Get compressed memory
""",
            category=ToolCategory.CATEGORY_BUILTINS,
            auth_config = {},
        )

    def set_compressed_memory_storage_value(self, compressed_id: str, original_content: str, compressed_content: str, 
                                        message_type: str, tokens_original: int, 
                                        tokens_compressed: int, compression_algorithm: str) -> None:
        """
        Set a compressed memory value in the database storage.

        This function stores a new compressed message in the database using the provided compressed_id.

        Parameters:
        compressed_id (str): The unique identifier for the compressed message.
        original_content (str): The full, uncompressed message content.
        compressed_content (str): The compressed version of the message.
        message_type (str): Type of message (e.g., "HumanMessage" or "AIMessage").
        tokens_original (int): Number of tokens in the original message.
        tokens_compressed (int): Number of tokens in the compressed message.
        compression_algorithm (str): The algorithm used for compression.

        Raises:
        ValueError: If any of the provided values are invalid.
        """
        if not all([compressed_id, original_content, compressed_content, message_type, compression_algorithm]):
            raise ValueError("All string parameters must be non-empty.")
        if tokens_original <= 0 or tokens_compressed <= 0:
            raise ValueError("Token counts must be positive integers.")

        compression_ratio = tokens_compressed / tokens_original if tokens_original > 0 else 0

        new_message = CompressedHistoryMessage(
            compressed_id=compressed_id,
            original_content=original_content,
            compressed_content=compressed_content,
            message_type=message_type,
            tokens_original=tokens_original,
            tokens_compressed=tokens_compressed,
            compression_ratio=compression_ratio,
            compression_algorithm=compression_algorithm
        )
        
        with Session(engine) as session:
            session.add(new_message)
            session.commit()
            session.refresh(new_message)

        logger.debug(f"Compressed message stored successfully: id = {compressed_id}")

    def retreive_full_data_for_compressed_message(self, compressed_id: str) -> Optional[CompressedHistoryMessage]:
        """
        Retrieves full data for a compressed message from the database using its compressed_id.
        Args:
        compressed_id (str): Unique identifier for the compressed message.
        Returns:
        Full message content.
        """
        if not isinstance(compressed_id, str) or not compressed_id:
            raise ValueError("compressed_id must be a non-empty string.")

        logger.debug(f"Retrieving full data for compressed_id: {compressed_id}")
        
        with Session(engine) as session:
            # Use a LIKE query to match partial compressed_id
            statement = select(CompressedHistoryMessage.original_content).where(CompressedHistoryMessage.compressed_id == compressed_id)
            message = session.exec(statement).first()
            
        if message:
            logger.debug(f"Full data retrieved for {compressed_id} = {message}")
            return message
        else:
            logger.debug(f"No data found for compressed_id: {compressed_id}")
            return None
    
    def get_tools(self) -> list[Callable]:
        logger.debug("Retrieving tools for MemoryCompressionTool")
        return self.wrap_tool_functions([
            self.retreive_full_data_for_compressed_message
        ])