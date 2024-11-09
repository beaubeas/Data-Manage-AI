from typing import List, Callable
import requests
from datetime import datetime
import os

from supercog.engine.tool_factory import ToolFactory, ToolCategory, LLMFullResult, LangChainCallback


class EmotionLogicTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="emotion_logic",
            system_name="Emotion Logic",
            logo_url="",
            auth_config={
                "strategy_token": {
                    "api_key": "The API key for the emotion analysis service",
                    "api_key_password": "The password for the API key",                    
                },
            },
            category=ToolCategory.CATEGORY_SPEECH,
            help="""
Use the Emotion Logic speech sentiment analysis API
""",
        )

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            self.analyze_file,
        ])

    async def analyze_file(self, filename: str, callbacks: LangChainCallback) -> str:
        """ Analyze sentiment in a speech file using the Emotion Logic API."""

        url = "https://cloud.emlo.cloud/analysis/analyzeFile"
        params = {"outputType": "json"}
        #auth = ("4e29d65e-9d4c-4a4f-89f9-6870afa74361", "4ZUYBBM@IW%54@BI%F7IB$PG62)(M9HK^X!24C9T#T^$(D9)1!@V)^B@6XY!(*5)")
        auth = (self.credentials.get("api_key"), self.credentials.get("api_key_password"))

        data = {
            "apiKey":self.credentials.get("api_key"),
            "apiKeyPassword": self.credentials.get("api_key_password"),
            "useSpeechToText": "True",
            "sensitivity": "normal",
            "consentObtainedFromDataSubject": "True",
            "requestId": f"msa_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }

        if not os.path.exists(filename):
            return f"Error: File '{filename}' not found."

        files = {
            "file": (filename, open(filename, "rb"))
        }        

        response = requests.post(url, params=params, auth=auth, data=data, files=files)

        await self.log(f"Status Code: {response.status_code}\n", callbacks)
        await self.log(f"Response Content: {response.text}\n", callbacks)

        return response.text
    
