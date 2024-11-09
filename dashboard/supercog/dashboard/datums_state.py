import reflex as rx
import pandas as pd

from .global_state import GlobalState
from .state_models import UIDatum
from .models import Agent
import os
import json
import io

from typing import List, Optional, Dict, Union

import traceback
import requests

from PIL import Image

import base64

import datetime

import mimetypes

import logging

logger = logging.getLogger('datums')
#logging.basicConfig(level=logging.DEBUG)

class DatumsState(GlobalState):
    #datums: dict[str, list[UIDatum]] = {}
    datums:        List[UIDatum] = []
    _agent_id:     str = ""
    agent_name:    str = ""
    agent_avatar:  str = ""
    _run_id:       str = ""
    
    dlist = []
    flat_structure: List[Dict[str, Union[str, bool, int]]] = []  
    
    # Global datum response attributes
    file_type:   str = ""
    datum_type:  str = ""
    file_source: str = "SupercogFS"
    datum_name:  str = ""

    # Media-related attributes
    s3_url:       str = ""
    media_url:    str = ""
    raw_data:     str = ""
    media_player: str = ""
    media_debug:  str = ""

    # Image-specific attributes
    image_data_present: bool = False
    encoded_image:      str = ""
    image_debug:        str = ""
    
    # File information attributes
    file_created:       str = ""
    file_modified:      str = ""
    file_size:          str = ""
    file_info_markdown: str = ""
    
    # File path attributes
    file_path:            str = ""
    file_name_restricted: str = ""
    
    # Content-specific attributes
    table_data: pd.DataFrame = pd.DataFrame([])
    text_data:  str = ""
    json_data:  dict = {}
    dir_data:   str = ""
    pdf_text:   str = ""

    # Email-specific attributes
    email_subject: str = ""
    email_sender: str = ""
    email_recipient: str = ""
    email_date: str = ""
    email_body: str = ""
    is_html:    str = "False"
    
    @rx.var
    def item_count(self) -> int:
        return len(self.flat_structure)

    def on_mount(self):
        """
        Initialization routine to mount the component, fetch datums recursively
        and organize them by category. It sets up the initial state of the viewer 
        component once the component is mounted on the front-end.
        """
        self._agent_id = self.router.page.params.get("appid")
        self._run_id = self.router.page.params.get("run_id")
        
        with rx.session() as sess:
            agent = sess.get(Agent, self._agent_id)
            if agent is not None:
                self.agent_name = agent.name
                self.agent_avatar = agent.avatar_url or "/robot_avatar2.png"

        #print("Datums are:",self.datums)
        self.flat_structure = self.flatten_datums(self.datums)
        self.datums = self.fetch_datums_recursive(
            self.user.tenant_id,
            self._agent_id,
            self.user.id,
            self._run_id
        )
        self.update_flat_structure()

        
    def mount_single(self):
        self._agent_id = self.router.page.params.get("appid")
        self._run_id = self.router.page.params.get("run_id")

        file_name = self.router.page.params.get("file")
        datum = UIDatum(category="files",
                        name=file_name,
                        path=file_name,
                        mime_type="",
                        datum_type="",
                        is_directory=False)
        return self.load_datum(datum)
    
    def mime_type_to_datum_type(self, mime_type: str, file_name: str) -> str:
        if mime_type == "application/pdf":
            return "pdf"
        elif mime_type == "application/rls-services+xml":
            return "text"
        elif mime_type == "text/plain":
            return "text"
        elif mime_type == "application/javascript":
            return "text"
        elif mime_type == "application/json":
            return "text"
        elif mime_type == "audio/x-wav":
            return "audio"
        elif mime_type == "audio/mpeg":
            return "audio"
        elif mime_type == "audio/mp4a-latm":
            return "audio"
        elif mime_type == "image/jpeg":
            return "image"
        elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            return "csv"
        elif mime_type == "text/csv":
            return "csv"
        else:
            return "text"
        
    def fetch_datums_recursive(self, tenant_id, agent_id, user_id, run_id, directory=None) -> List[UIDatum]:
        datums = self._agentsvc.get_run_datums(tenant_id, agent_id, user_id, run_id, directory)
        result = []
        for datum in datums:
            datum_obj = UIDatum(**datum.dict())  # Use dict() instead of model_dump() if datum is a Pydantic model
            datum_obj.path = os.path.join(directory or '', datum_obj.name)
            datum_obj.is_directory = datum_obj.mime_type == 'inode/directory'
            if datum_obj.is_directory:
                datum_obj.children = self.fetch_datums_recursive(
                    tenant_id, agent_id, user_id, run_id, datum_obj.path
                )
            result.append(datum_obj)
            #print(f"Loaded datum: name={datum_obj.name}, mime_type={datum_obj.mime_type}, "
            #      f"is_directory={datum_obj.is_directory}, path={datum_obj.path}")
        return result

    def flatten_datums(self,
                       datums: List[UIDatum],
                       parent_path: str = "") -> List[Dict[str, Union[str, bool, int, str]]]:
        result = []
        directories = []
        files = []

        for datum in datums:
            full_path = os.path.join(parent_path, datum.name)
            level = full_path.count(os.sep)
            item = {
                "path": full_path,
                "name": datum.name,
                "mime_type": datum.mime_type,
                "datum_type": self.mime_type_to_datum_type(datum.mime_type, datum.name),
                "is_directory": datum.is_directory,
                "is_expanded": datum.is_expanded,
                "level": level,
                "indentation": f"{level}em"
            }

            if datum.is_directory:
                directories.append(item)
                if datum.is_expanded:
                    item["children"] = self.flatten_datums(datum.children, full_path)
            else:
                files.append(item)

        # Sort directories and files separately
        directories.sort(key=lambda x: x["name"].lower())
        files.sort(key=lambda x: x["name"].lower())

        # Combine sorted directories and files
        result = directories + files

        return result
    

    def update_flat_structure(self):
        self.flat_structure = self.flatten_and_expand(self.flatten_datums(self.datums))

    def flatten_and_expand(self, items):
        result = []
        for item in items:
            result.append(item)
            if item["is_directory"] and item["is_expanded"] and "children" in item:
                result.extend(self.flatten_and_expand(item["children"]))
        return result

    def toggle_expand(self, path: str):
        def toggle_recursive(datums: List[UIDatum]):
            for datum in datums:
                if datum.path == path:
                    datum.is_expanded = not datum.is_expanded
                    return True
                if datum.is_directory:
                    if toggle_recursive(datum.children):
                        return True
            return False

        toggle_recursive(self.datums)
        self.update_flat_structure()

    def handle_item_click(self, path: str):
        #print(f"Handling click for path: {path}")
        def handle_recursive(datums: List[UIDatum]):
            for datum in datums:
                if datum.path == path:
                    if datum.is_directory:
                        self.toggle_expand(path)
                        self.load_datum(datum)
                    else:
                        self.load_datum(datum)
                    return True
                if datum.is_directory:
                    if handle_recursive(datum.children):
                        return True
            return False

        handle_recursive(self.datums)
   
    def refresh(self):
        """
        Refreshes the data view by re-mounting the data viewer component.
        This effectively re-fetches data from the agent service.
        """
        self.on_mount()

    def init_state(self):
        """ These attributes represent the current file or directory selected in the datums pane.
            Since they are reused each time rather than an instance for each one we need to
            initialize the shared variables each time through so the current one doesn't get
            values from the last one.
        """
        self.file_source          = "SupercogFS"
        self.image_data_present   = False
        self.encoded_image        = ""
        self.image_debug          = ""
        # Media-related attributes
        self.s3_url               = ""
        self.media_url            = ""
        self.raw_data             = ""
        self.media_player         = ""
        self.media_debug          = ""
        self.file_created         = ""
        self.file_modified        = ""
        self.file_size            = ""
        self.file_info_markdown   = ""

        # File path attributes
        self.file_path            = ""
        self.table_data           = pd.DataFrame([])
        self.text_data            = ""
        self.json_data            = {}
        self.dir_data             = ""
        self.pdf_text             = ""
        self.file_name_restricted = ""
            
    def load_datum(self, datum: Union[UIDatum, str]):
        """
        Loads a specific datum into the view state for display.
        Args:
            datum (UIDatum): The UIDatum object representing the selected datum.
        """
        self.init_state()
        self.file_name_restricted = datum.name

        if isinstance(datum, str):
            # If datum is a string (path), find the corresponding UIDatum object
            datum = next((d for d in self.datums if d.path == datum), None)
            if datum is None:
                print(f"No datum found for path: {datum}")
                return

        self.datum_name = datum.name
        try:
            type, content = self._agentsvc.get_run_datum(
                self.user.tenant_id, 
                self._agent_id, 
                self.user.id, 
                self._run_id, 
                datum.category,
                datum.path,
            )
        except Exception as e:
            print(f"Exception in load_datum for {self.datum_name}:")
            print(traceback.format_exc())
            type = "error"
            content = str(e)

        self.file_type = type  
        self.datum_type = type

        if isinstance(content, dict):
            self.generate_file_info_markdown(content)
        else:
            # If content is not a dict, it's likely an error message string
            self.generate_file_info_markdown({})

        # Process different file types
        if type in ["audio", "video", "image"]:
            self.process_media_content(content)
        elif type == "csv":
            if isinstance(content, dict) and isinstance(content.get('raw_data'), pd.DataFrame):
                self.table_data = content['raw_data']
            else:
                self.table_data = pd.DataFrame()
        elif type in ["text", "pdf", "dir"]:
            self.text_data = content.get('raw_data', '') if isinstance(content, dict) else content
            self.datum_type = "text"
        elif type == "email":
            self.load_email_data(content)
        elif type == "json":
            if isinstance(content, dict):
                raw_json = content.get('raw_data', '{}')
            else:
                raw_json = content
            if isinstance(raw_json, str):
                try:
                    self.json_data = json.loads(raw_json)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON: {raw_json}")
                    self.json_data = {}
            else:
                self.json_data = raw_json
        elif type == "error":
            self.text_data = content if isinstance(content, str) else content.get('raw_data', 'An error occurred while loading the file')
            self.datum_type = "text"
        else:
            logger.warn(f"Unhandled file type: {type}")
            self.text_data = f"Unhandled file type: {type}"
            self.datum_type = "text"
            
    def load_email_data(self, content: dict):
        email_data = json.loads(content.get('raw_data', '{}')) if isinstance(content.get('raw_data'), str) else content.get('raw_data', {})
        self.email_subject = email_data.get('subject') or 'N/A'
        self.email_sender = email_data.get('sender') or 'N/A'
        self.email_recipient = email_data.get('to') or 'N/A'
        self.email_date = email_data.get('date') or 'N/A'

        # Detect whether the body is plain text or HTML and handle accordingly
        if 'html' in email_data.get('body', {}):
            self.email_body = email_data.get('body', {}).get('html')  # Handle HTML
            self.is_html = True
        else:
            self.email_body = email_data.get('body', {}).get('plain') or 'N/A'
            self.is_html = False
        
    def process_media_content(self, content: dict):
        logger.debug(f"\n\nStarting process_media_content")
        logger.debug(f"\nContent received: {content}\n")

        self.file_source = "S3" if content.get('s3_url') else "SupercogFS"
        logger.debug(f"File source: {self.file_source}")

        # Process S3 URL
        full_s3_url = content.get('s3_url', '')
        self.s3_url = full_s3_url.split('?')[0] if full_s3_url else ''
        logger.debug(f"S3 URL: {self.s3_url}")

        self.file_path = content.get('file_path', '')
        logger.debug(f"File path: {self.file_path}")

        self.raw_data = content.get('raw_data', '')

        if self.s3_url:
            self.media_url = full_s3_url
            logger.debug(f"Using S3 URL as media URL: {self.media_url}")
        elif self.raw_data:
            mime_type = content.get('mime_type') or self.get_mime_type(content.get('type', ''))
            logger.debug(f"Determined MIME type: {mime_type}")
            self.media_url = f"data:{mime_type};base64,{self.raw_data}"
            logger.debug(f"Created data URL (truncated): {self.media_url[:50]}...")
        else:
            self.media_debug += f"Failed to create a playable URL.\n"
            logger.warn(f"Failed to create a playable URL")

        media_type = content.get('type', '')
        if media_type in ['audio', 'video']:
            logger.debug(f"Creating media player for {media_type}")
            self.create_media_player(media_type)
        elif media_type == 'image':
            logger.debug("Processing image")
            self.encoded_image = self.media_url
            logger.debug(f"Encoded image (truncated): {self.encoded_image[:50]}...")

        # Process file information
        self.file_created = content.get('created') or 'N/A'
        self.file_modified = content.get('modified') or 'N/A'
        self.file_size = content.get('size') or 'N/A'
        logger.debug(f"\nFile info - Created: {self.file_created}, Modified: {self.file_modified}, Size: {self.file_size}")

        logger.debug("Finished processing media content\n\n")

    def get_mime_type(self, media_type: str):
        if media_type == "audio":
            return "audio/mpeg"
        elif media_type == "video":
            return mimetypes.guess_type(self.file_path)[0] or "video/mp4"
        elif media_type == "image":
            return mimetypes.guess_type(self.file_path)[0] or "image/jpeg"
        return "application/octet-stream"
        

    def generate_file_info_markdown(self, content):
        logger.debug(f"generate_file_info_markdown called with content type: {type(content)}")
        #logger.debug(f"Content: {json.dumps(content, indent=2) if isinstance(content, dict) else str(content)[:200]}")

        # Use ':--' to left-justify the Value column
        table_content = "|  |  |\n|-----------|:------|\n"
        
        if not isinstance(content, dict):
            logger.error(f"Content is not a dictionary. Type: {type(content)}")
            table_content += f"| Error: | Content is not in expected format |\n"
            self.file_info_markdown = table_content
            return

        logger.debug("Processing file source")
        file_source = "S3" if content.get('s3_url') else "SupercogFS"
        table_content += f"| Source: | {file_source} |\n"
        
        logger.debug("Processing S3 URL or file path")
        if content.get('s3_url'):
            s3_url = content['s3_url'].split('?')[0]
            table_content += f"| S3 URL: | {s3_url} |\n"
        else:
            table_content += f"| Path: | {content.get('file_path', 'N/A')} |\n"
        
        logger.debug("Processing created timestamp")
        table_content += f"| Created: | {content.get('created', 'N/A')} |\n"
        
        logger.debug("Processing modified timestamp")
        table_content += f"| Modified: | {content.get('modified', 'N/A')} |\n"
        
        logger.debug("Processing file size")
        table_content += f"| Size: | {content.get('size', 'N/A')} |\n"
        
        logger.debug(f"Final table content: {table_content}")
        self.file_info_markdown = table_content


    def create_media_player(self, media_type: str):
        media_id = f"media_{hash(self.media_url or self.raw_data)}"
        mime_type = self.get_mime_type(media_type)
        src = self.media_url or f"data:{mime_type};base64,{self.raw_data}"
        
        if media_type == "audio":
            self.media_player = f"""
            <audio id="{media_id}" controls style="width: 300px; height: 40px; border-radius: 20px;">
                <source src="{src}" type="{mime_type}">
                Your browser does not support the audio element.
            </audio>
            """
        elif media_type == "video":
            self.media_player = f"""
            <video id="{media_id}" controls style="max-width: 100%; max-height: 300px;">
                <source src="{src}" type="{mime_type}">
                Your browser does not support the video element.
            </video>
            """

    def get_mime_type(self, media_type: str):
        if media_type == "audio":
            return "audio/mpeg"
        elif media_type == "video":
            return mimetypes.guess_type(self.file_path)[0] or "video/mp4"
        elif media_type == "image":
            return mimetypes.guess_type(self.file_path)[0] or "image/jpeg"
        return "application/octet-stream"

    def delete_datum(self, datum: UIDatum):
        print("Delete datum: ", datum)
        self._agentsvc.delete_run_datum(
            self.user.tenant_id, 
            self._agent_id, 
            self.user.id, 
            self._run_id, 
            datum['category'],
            datum['name'],
        )
        self.refresh()
