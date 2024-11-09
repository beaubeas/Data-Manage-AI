import io
import json
from contextlib import contextmanager
from urllib.parse import urlparse, parse_qs

from typing import Callable, Any, Optional
from supercog.engine.tool_factory import ToolFactory, ToolCategory

from google.oauth2.credentials import Credentials as GoogleOauth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import google_auth_oauthlib.helpers
import google.auth.exceptions
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
import os
from datetime import datetime
import pandas as pd

from supercog.shared.services import config
from supercog.shared.logging import logger
from supercog.shared.oauth_utils import google_refresh_token
from .gmail_tool import GAuthCommon

# If modifying these scopes, delete the file token.json.
#SCOPES = config.get_global("GSUITE_SCOPES").split(",")

SCOPES = [
    # https://developers.google.com/docs/api/auth
    # https://developers.google.com/drive/api/guides/api-specific-auth
    #
    # This is the magic scope that allows us access to files and folders shared explicitly with our app by
    # the user. We think Google will allow this scope to be approved. The trick with this scope is that
    # docs have to be shared explicitly by using the FilePicker API
    'https://www.googleapis.com/auth/drive.file', 

    # This is the "see all" scope which Google will not approve without a fight, althugh somehow it is listed
    # as only "Sensitive" as opposed to Restricted.
    #'https://www.googleapis.com/auth/documents',

    # This one is labeled "Restricted" which is the most severe:
    # 'https://www.googleapis.com/auth/drive.readonly',

    # These are mostly pro-forma but we should determine if we need these or not
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

class GoogleDocsTool(ToolFactory, GAuthCommon):
    def __init__(self):
        super().__init__(
            id = "google_docs_connector",
            system_name = "Google Docs",
            logo_url=super().logo_from_domain("google.com"),
            category=ToolCategory.CATEGORY_FILES,
            help="""
Access Google Docs, Sheets and Slides. You must create your own Oauth client.
Please review the [documentation](https://github.com/supercog-ai/community/wiki/Tool-Library-Docs#google-docs-tool).
""",
            auth_config = {
                "strategy_oauth": {
                    "help": "Login to Google to connect your account.",
                    "env_vars": "GDOCS_CLIENT_ID,GDOCS_CLIENT_SECRET",
                }
            },
            oauth_scopes=SCOPES,
            tool_uses_env_vars=True,
        )

    def get_scopes(self) -> list[str]:
        return SCOPES

    def check_for_client_env_vars(self) -> str|None:
        self.google_client_id = self.run_context.get_env_var("GDOCS_CLIENT_ID")
        self.google_client_secret = self.run_context.get_env_var("GDOCS_CLIENT_SECRET")

        missing = []
        if not self.google_client_id:
            missing.append("GDOCS_CLIENT_ID")
        if not self.google_client_secret:
            missing.append("GDOCS_CLIENT_SECRET")

        if missing:
            return f"You must set these env vars: {', '.join(missing)}"
        return None

    def get_oauth_client_id_and_secret(self) -> tuple[str|None, str|None]:
        return config.get_global("GSUITE_CLIENT_ID"), config.get_global("GSUITE_CLIENT_SECRET")

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([ 
           self.list_drives,
           self.search_for_docs,
           self.download_doc,
        ])

    def list_drives(self):
        """ List the available Google Drives """
        err = self.check_for_client_env_vars()
        if err:
            return err
        
        with self.get_service() as service:
            drives = []
            for drive in service.drives().list().execute()['drives']:
                drives.append({"name": drive['name'], "id": drive['id']})
            return json.dumps(drives)

    def search_for_docs(
        self,
        name_search: str, 
        number_of_results: int = 5,
        ) -> str:
        """ Searches your Google Drive for files matching the name_search parameter. """
        err = self.check_for_client_env_vars()
        if err:
            return err
        with self.get_service() as service:
            results = service.files().list(
                q=f"name contains '{name_search}'",
                fields="files(id, name, webViewLink)",
                orderBy="modifiedTime desc",
                pageSize=number_of_results,
            ).execute()
            items = results.get('files', [])
            return json.dumps(items)

    def download_doc(
        self,
        doc_id: str|None=None,
        doc_name: str|None=None,
        doc_link: str|None=None,
        ) -> str|dict:
        """ Downloads the Google Doc identified by one of the doc_id, name, or its link.
            Returns the content of the file as plain text.
        """
        err = self.check_for_client_env_vars()
        if err:
            return err
        with self.get_service() as service:
            if doc_id:
                doc = service.files().get(fileId=doc_id).execute()
            elif doc_name:
                results = service.files().list(
                    q=f"name = '{doc_name}'",
                    fields="files(id, name, webViewLink,mimeType,modifiedTime)",
                    orderBy="modifiedTime desc",
                    pageSize=1,
                ).execute()
                items = results.get('files', [])
                if items:
                    doc = items[0]
                else:
                    return f"Could not find a document named '{doc_name}'."
            elif doc_link:
                fileId = self.extract_file_id_from_link(doc_link)
                if fileId:
                    print("Downloading file by ID: ", fileId)
                    doc = service.files().get(fileId=fileId).execute()
                else:
                    return "Error, cannot determine file ID from link: " + doc_link

            return self.download_doc_content(service, doc)

    def download_doc_content(self, service, doc) -> str|dict:
        mime = doc['mimeType']
        if mime == "text/plain":
            return service.files().get_media(fileId=doc['id']).execute()
        
        if mime in [
            "application/vnd.google-apps.document", 
            "application/vnd.google-apps.presentation",
            ]:
            # Download a doc as text
            req_mime = "text/plain"
        elif mime == "application/vnd.google-apps.spreadsheet":
            # Dowmload a sheet as csv
            req_mime = "text/csv"
            content = service.files().export(fileId=doc['id'], mimeType=req_mime).execute()
            return self.get_dataframe_preview(pd.read_csv(io.StringIO(content)))
        else:
            return "Error: Unsupported file type: " + mime
        return service.files().export(fileId=doc['id'], mimeType=req_mime).execute()

    def extract_file_id_from_link(self, link: str):
        # Split the URL into parts
        parts = link.split('/')
        # The fileId is usually the segment after '/d/'
        for i, part in enumerate(parts):
            if part == 'd' and i + 1 < len(parts):
                return parts[i + 1]
        # See if we just have id= in the query string
        # urlparse the link
        parsed_url = urlparse(link)
        query = parse_qs(parsed_url.query)
        return query.get('id', [None])[0]

    @contextmanager
    def get_service(self):
        tokens = self.credentials['tokens']
        if isinstance(tokens, str):
            tokens = json.loads(tokens)
        yield build(
            'drive', 
            'v3',
            credentials=GoogleDocsTool.setup_credentials(
                tokens, 
                SCOPES, 
                [self.google_client_id, self.google_client_secret],
            )
        )

