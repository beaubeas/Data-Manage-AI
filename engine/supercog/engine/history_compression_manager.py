from typing import List, Dict, Union
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.schema.runnable import RunnableBinding
from langchain_openai import ChatOpenAI
from .tools.memory_compression_tool import MEMORY_COMPRESSION_TOOL_ID, MemoryCompressionTool
from supercog.shared.models import AgentBase, ToolBase
import hashlib
from supercog.shared.logging import logger
import uuid
from openai import OpenAI
from supercog.shared.services import config
import json

Message = Union[HumanMessage, AIMessage, SystemMessage]

MODEL_NAME = "gpt-4o-mini"
COMPRESSION_THRESHOLD = 2000

class HistoryCompressionManager:
    def __init__(self):
        # Initialize the LLM with GPT-4
        self.memory_compression_tool = MemoryCompressionTool()
        self.retrieve_function_name = self.memory_compression_tool.retreive_full_data_for_compressed_message.__name__
        self.client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))
        self.compression_cache = {}


    def should_compress(self, message: Union[HumanMessage, AIMessage], char_threshold: int = COMPRESSION_THRESHOLD, enabled_tools: List[ToolBase] = []) -> bool:
        if self._is_retrieve_function_call(message):
            return False

        # Check if the compressed text retriever is available
        has_compressed_text_retriever = any(tool.tool_factory_id == MEMORY_COMPRESSION_TOOL_ID for tool in enabled_tools)

        # If the compressed text retriever is not available, don't compress
        if not has_compressed_text_retriever:
            return False

        # Check if the message is already compressed
        if message.content.startswith("COMPRESSED_MESSAGE:"):
            return False
        
        # Check if the message exceeds the character threshold
        if len(message.content) > char_threshold:
            return True
        
        return False
    
    def compress_message_with_llm(self, message: Union[HumanMessage, AIMessage]) -> Union[HumanMessage, AIMessage]:
        system_prompt = "You are an AI assistant tasked with compressing chat history messages to reduce token usage while preserving essential information. Your goal is to create a concise summary of the original message that captures its key points and structure."
        
        user_prompt = f"""
Given a chat message, follow these steps:

1. Analyze the content and structure of the message.
2. Identify the main topic or purpose of the message.
3. Look for any structured data (e.g., tables, lists, code snippets) or long-form text.
4. For structured data:
   - Provide a brief description of the data type and its contents.
   - Summarize key statistics (e.g., number of rows/items, column names for tables).
   - Include a small sample of the data (e.g., first 3 and last 3 items for lists or tables).
   - Note any important patterns or ranges in the data.
5. For long-form text:
   - Summarize the main points in bullet form.
   - Preserve any crucial details or numbers.
   - Indicate if any specific sections were omitted.
6. For code snippets:
   - Mention the programming language.
   - Describe the purpose of the code.
   - Include only the most important parts of the code, if any.
7. Preserve any direct questions or action items from the original message.
8. Add a note at the end indicating that this is a compressed version and full details are available on request.

Compress the following message:

{message.content}

IMPORTANT: Provide ONLY the final compressed result. Do not include any introductory statements, explanations, or additional comments. The output should start directly with the compressed content.
"""

        response = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "text"},
        )

        compressed_content = response.choices[0].message.content

        # Generate a unique UUID for this compressed message
        message_uuid = str(uuid.uuid4())[:6]

        # Store the original message with its UUID     
        logger.info("Saving compressed message with id %s", message_uuid)

        compressed_content = response.choices[0].message.content

        # Calculate token counts
        original_tokens = len(message.content)
        compressed_tokens = len(compressed_content)

        # Store the original message with its UUID using the new method
        self.memory_compression_tool.set_compressed_memory_storage_value(
            compressed_id=message_uuid,
            original_content=message.content,
            compressed_content=compressed_content,
            message_type="HumanMessage" if isinstance(message, HumanMessage) else "AIMessage",
            tokens_original=original_tokens,
            tokens_compressed=compressed_tokens,
            compression_algorithm=MODEL_NAME
        )

        final_content = f"<COMPRESSED_MESSAGE_ID>{message_uuid}</COMPRESSED_MESSAGE_ID>\n\n{compressed_content}\n\nFull content available via access with id: {message_uuid}"
        
        # Return the same type of message that was input
        if isinstance(message, HumanMessage):
            return HumanMessage(content=final_content)
        else:
            return AIMessage(content=final_content)

    def process_chat_history(self, x: Dict[str, Union[str, List[Message]]], enabled_tools: List[ToolBase]) -> List[Message]:
        self._log_chat_history(x, enabled_tools)
        
        compressed_history = self._compress_history(x["chat_history"], enabled_tools)
        
        x["chat_history"] = compressed_history
        self._log_compressed_history(x)
        
        return compressed_history

    def _log_chat_history(self, x: Dict[str, Union[str, List[Message]]], enabled_tools: List[ToolBase]) -> None:
        logger.debug(f"process_chat_history Tools: \n{enabled_tools}")
        logger.debug(f"Chat history: \n{x}\n\n\nEND CHAT HISTORY\n\n\n")

    def _log_compressed_history(self, x: Dict[str, Union[str, List[Message]]]) -> None:
        logger.debug(f"Chat history compressed: \n{x}\n\n\nEND CHAT HISTORY\n\n\n")

    def _compress_history(self, chat_history: List[Message], enabled_tools: List[ToolBase]) -> List[Message]:
        compressed_history = []

        for i, message in enumerate(chat_history):
            if self._is_retrieve_function_call(message):
                logger.debug(f"Setting content empty for function call message {i}: {message.content[:100]}...")
                message = message.__class__(content=".") # Set the content to empty string. Claude requires not empty content
            if self.should_compress(message, enabled_tools=enabled_tools):
                # Generate MD5 hash of the message content
                message_hash = hashlib.md5(message.content.encode()).hexdigest()
                
                
                # Check if the message hash is already in the cache
                if message_hash in self.compression_cache:
                    logger.debug(f"Using cached compressed message for message {i}")
                    compressed_message = self.compression_cache[message_hash]
                else:
                    logger.debug(f"Compressing message {i}: {message.content[:100]}...")
                    compressed_message = self.compress_message_with_llm(message)
                    # Store the compressed message in the cache
                    self.compression_cache[message_hash] = compressed_message
                
                compressed_history.append(compressed_message)
            else:
                logger.debug(f"Keeping message {i} without compression: {message.content[:100]}...")
                compressed_history.append(message)
        
        logger.debug(f"Compression complete. Original history length: {len(chat_history)}, Compressed history length: {len(compressed_history)}")
        return compressed_history

    def _is_retrieve_function_call(self, message: Message) -> bool:
        if not isinstance(message, HumanMessage):
            return False
        
        content = message.content
        if isinstance(content, str):
            # Check if the content contains the function call without parsing as JSON
            return f"'function_call': '{self.retrieve_function_name}'" in content
        
        return False
