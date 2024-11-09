from typing import Dict, Any
import traceback

from supercog.shared.services import config

from supercog.engine.tool_factory import ToolCategory
from supercog.engine.doc_source_factory import DocSourceFactory
from supercog.engine.rag_utils import get_ragie_partition

from pydantic import Field
import requests
from urllib.parse import quote

class GoogleDriveDocSource(DocSourceFactory):
    connection_id: str = Field(default=None)
    
    def __init__(self):
        super().__init__(
            id="google_drive_file_source",
            system_name="Docs from Google Drive",
            logo_url=super().logo_from_domain("google.com"),
            category=ToolCategory.CATEGORY_DOCSRC,
            auth_config={
                "strategy_oauth": {
                    "help": "Login to Google to connect your account.",
                    "url_function": "initialize_oauth",
                }
            },
            help="""
Load documents from Google Drive (Connection must be established through Ragie!)
""",
        )

    def get_authorize_url(self, tenant_id: str, user_id: str, index_id: str, source_id: str) -> str:
        """
        Initialize Ragie OAuth flow and return the redirect URL
        """
        try:
            ragie_api_key = config.get_global("RAGIE_API_KEY", required=False) or ""
            
            redirect_url = super().get_callback_url(
                # this enmeshment makes me uncomfortable
                dashboard_path=f"/sconnections/index/{index_id}",
                tenant_id=tenant_id, 
                user_id=user_id, 
                index_id=index_id, 
                source_id=source_id
            )
            # Get the configured domain for redirect
            
            headers = {
                "Authorization": f"Bearer {ragie_api_key}",
                "Content-Type": "application/json"
            }
                       
            payload = {
                "source_type": "google_drive",
                "redirect_uri": redirect_url,
                "metadata": {},
                "mode": "hi_res",
                "partition": get_ragie_partition(tenant_id, index_id)
            }

            # Get the Ragie OAuth URL
            response = requests.post(
                "https://api.ragie.ai/connections/oauth",
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Failed to initialize Ragie OAuth: {response.text}")
            
            return response.json()["url"]
            
        except Exception as e:
            traceback.print_exc()
            raise RuntimeError(f"Error initializing Ragie OAuth: {str(e)}")
        