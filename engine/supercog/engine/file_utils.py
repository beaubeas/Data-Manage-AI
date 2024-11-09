import json
import os
import re
import mimetypes
from fastapi import FastAPI, Depends, HTTPException

from fastapi.responses import JSONResponse, FileResponse, Response
import pandas as pd
from io import BytesIO
import PyPDF2
from typing import Dict, Any, Union
import email
from email import policy
from email.parser import BytesParser
from supercog.engine.email_utils import process_email

def read_eml(file: Union[str, BytesIO], agent_dir: str, run_context) -> Dict[str, Any]:
    """
    Reads an .eml file and returns a structured representation of its contents.

    Args:
        file (Union[str, BytesIO]): Either a file path as a string or a BytesIO object containing the .eml data.
        agent_dir (str): The directory to save attachments.
        run_context: The run context for file operations.

    Returns:
        Dict[str, Any]: A dictionary containing the parsed email content and information about saved attachments.
    """
    if isinstance(file, str):
        with open(file, 'rb') as file_obj:
            email_message = email.message_from_binary_file(file_obj)
    elif isinstance(file, BytesIO):
        email_message = email.message_from_binary_file(file)
    else:
        raise ValueError("Input must be either a file path string or a BytesIO object")
    
    return process_email(email_message, agent_dir, run_context)

def read_pdf(file: Union[str, BytesIO]) -> str:
    """
    Reads a PDF file and extracts text from all pages.

    Args:
        file (Union[str, BytesIO]): Either a file path as a string or a BytesIO object containing the PDF data.

    Returns:
        str: The extracted text from all pages of the PDF.
    """
    if isinstance(file, str):
        with open(file, 'rb') as file_obj:
            pdf_reader = PyPDF2.PdfReader(file_obj)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
    elif isinstance(file, BytesIO):
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
    else:
        raise ValueError("Input must be either a file path string or a BytesIO object")
    
    return text

def is_image_file(file_path: str):
    # Function to check if a file is an image

    # Define common image file extensions
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'}
    
    # Get the file extension
    _, ext = os.path.splitext(file_path)
    
    # Check if the file extension is in the set of image extensions
    if ext.lower() in image_extensions:
        # Determine the content type
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = "image/jpeg"  # default to JPEG if content type cannot be determined
        
        return content_type
    return None

def is_text_file(file_path: str) -> bool:
    # Simple check based on file extension, could be enhanced
    TEXT_EXTENSIONS = ['.txt', '.rs', '.py', '.java', '.apex', '.rdo', '.cbl', '.jc', '.yml', '.asm', '.exec', '.idcams', '.cpy', '.mac', '.xml', '.html', '.js', '.css', '.md']
    return any(file_path.endswith(ext) for ext in TEXT_EXTENSIONS)

def is_audio_file(file_path: str) -> bool:
    """
    Check if a given file path is an audio file based on its extension.
    Args:
        file_path (str): The path to the file.
    Returns:
        bool: True if the file is an audio file, False otherwise.
    """
    # List of common audio file extensions
    AUDIO_EXTENSIONS = ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a']
    return any(file_path.endswith(ext) for ext in AUDIO_EXTENSIONS)

def fix_json_string(input_string):
    # Remove any leading/trailing whitespace and quotes
    input_string = input_string.strip().strip('"')
    
    # Replace escaped newlines with actual newlines
    input_string = input_string.replace('\\n', '\n')
    
    # Correctly handle escaped double quotes within values by converting them to single quotes
    def replace_embedded_quotes(match):
        return match.group(1) + "'" + match.group(2) + "'" + match.group(3)
    
    input_string = re.sub(r'(".*?":\s*")([^"]*?)\\"([^"]*?)\\"(.*?)(".*?")', replace_embedded_quotes, input_string)
    
    # Remove invalid escape sequences like \ at the end of the string
    input_string = re.sub(r'\\$', '', input_string, flags=re.MULTILINE)
    
    # Correctly handle escaped double quotes within values
    input_string = re.sub(r'\\\\', r'\\', input_string)
    input_string = re.sub(r'\\"', r'"', input_string)
    
    # Remove invalid control characters
    input_string = re.sub(r'[\x00-\x1f\x7f]', '', input_string)
    
    return input_string

def get_icon_type(file_path: str) -> str:
    if is_image_file(file_path):
        return "image"
    if is_audio_file(file_path):
        return "audio"
    if file_path.endswith(".json"):
        return "json"
    elif file_path.endswith(".csv")  or \
         file_path.endswith(".xlsx") or \
         file_path.endswith(".parquet"):
       return "csv"
    return "text"
    
async def read_and_return_file(file_path: str) -> Response:
    try:
        df = None
        # Check for image files
        content_type = is_image_file(file_path)
        if content_type:
            return Response(content=file_path, media_type=content_type)
        with open(file_path, 'rb') as file:
            content = file.read()
            stats = os.stat(file_path)
            if is_text_file(file_path):
                language_type = None
                if file_path.endswith('.rs'):
                    language_type = "rust"
                elif file_path.endswith('.py'):
                    language_type = "python"
                elif file_path.endswith('.cbl'):
                    language_type = "cobol"
                elif file_path.endswith('.java'):
                    language_type = "java"
                elif file_path.endswith('.apex'):
                    language_type = "java"
                elif file_path.endswith('.sql'):
                    language_type = "sql"
                elif file_path.endswith('.js'):
                    language_type = "javascript"
                if language_type:
                    content = f"""
```{language_type}
{content.decode('utf-8')}
```
"""
                content_type = "text/plain" # this handles all other non language text files
            elif is_audio_file(file_path):
                content_type = "application/audio"
                content = file_path
            elif file_path.endswith(".json"):
                try:
                    #print(f"RAW  ===> {content.decode('utf-8')[0:5000]}")
                    json_compliant_string = fix_json_string(content.decode('utf-8'))
                    #print(f"JSON ===> {json_compliant_string[0:5000]}")
                    content = json.loads(json_compliant_string)
                    #print(f"Json.loads complete. {content}")
                    # Convert the parsed JSON back to a string before returning or processing further
                    content = json.dumps(content, indent=4)
                except Exception as e: #json.JSONDecodeError as e:
                    print(f"Error parsing JSON: {e}")
                    # leave content as is for display 
                content_type = "application/json"
            elif file_path.endswith(".csv"):
                df = pd.read_csv(file_path)
            elif file_path.endswith(".parquet"):
                df = pd.read_parquet(file_path)
            elif file_path.endswith(".xlsx"):
                df = pd.read_excel(file_path)
            else:
                content_type = "application/octet-stream"
            # If we had a data frame then return its content here    
            if df is not None:
                return Response(df.to_csv(), media_type="text/csv")
            return Response(content=content, media_type=content_type)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
