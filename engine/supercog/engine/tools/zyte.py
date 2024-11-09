import html2text

from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.services import config

from typing import Callable

import httpx

from .rest_tool_v2 import RESTAPIToolV2

class ZyteBase(ToolFactory):
    async def _get_api_response(self, url: str, get_screenshot: bool = False) -> httpx.Response:
        # if error then returns error message as the second element of the tuple
        api_key = self.run_context.get_env_var("ZYTE_API_KEY") or config.get_global("ZYTE_API_KEY", required=False)
        if api_key is None:
            raise RuntimeError("Error: no API key available for the Zyte API. Set the ZYTE_API_KEY environment variable.")
        
        async with httpx.AsyncClient() as client:
            auth = httpx.BasicAuth(username=api_key, password="")
            params = {
                "url": url, 
                "screenshot": True, 
                "screenshotOptions": {"fullPage":True}
            } if get_screenshot else {"url": url, "browserHtml": True}
            
            response = await client.post(
                "https://api.zyte.com/v1/extract",
                auth=auth,
                json=params,
                timeout=90,
            )
            response.raise_for_status()
            return response

class ZyteScraperTool(ZyteBase):
    def __init__(self):
        super().__init__(
            id = "zyte_scraping",
            system_name = "Zyte Web Scraping",
            logo_url="https://logo.clearbit.com/zyte.com",
            auth_config = { },
            category=ToolCategory.CATEGORY_INTERNET,
            tool_uses_env_vars=True,
            help="""
Use Zyte.com to scrape web pages
""",
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.scrape_web_page,
        ])

    async def scrape_web_page(self, url: str, return_format:str = "text") -> str:
        """ Returns the browser rendering content of a web page, usually HTML. 
            Will return either text or HTML depending on the return_format parameter.
        """
        response = await self._get_api_response(url, get_screenshot=False)
        response.raise_for_status()
        html = response.json()["browserHtml"]
        if return_format == "text":
            return html2text.html2text(html)
        else:
            return html

