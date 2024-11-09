from base64 import b64decode
import html2text

from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.services import config

from typing import Dict, List, Callable

import httpx

from .rest_tool_v2 import RESTAPIToolV2
from .zyte import ZyteBase

class ZyteScreenshotTool(ZyteBase):
    def __init__(self):
        super().__init__(
            id = "zyte_screenshot",
            system_name = "Zyte Web Screenshots",
            logo_url="https://logo.clearbit.com/zyte.com",
            auth_config = { },
            category=ToolCategory.CATEGORY_INTERNET,
            tool_uses_env_vars=True,
            help="""
Use Zyte.com to take web screenshots
""",
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.get_page_screenshot,
        ])

    async def get_page_screenshot(self, url: str) -> dict:
        """ Returns the image of the browser rendering content of a web page. """
        response = await self._get_api_response(url, get_screenshot=True)
        response.raise_for_status()
        screenshot: bytes = b64decode(response.json()["screenshot"])
        return await RESTAPIToolV2._process_image(screenshot)  # Read the image data as bytes



