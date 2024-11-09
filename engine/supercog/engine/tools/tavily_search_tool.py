from pprint import pprint

from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.services import config
from .scaleserp_browser import ScaleSerpBrowserTool

from typing import Dict, List, Callable
import pandas as pd

import httpx


class TavilySearchTool(ScaleSerpBrowserTool):
    def __init__(self):
        super().__init__(
            id = "tavily_search",
            system_name = "Web Search and Page Browser",
            logo_url="https://uxwing.com/wp-content/themes/uxwing/download/internet-network-technology/internet-browsing-icon.png",
            auth_config = { },
            category=ToolCategory.CATEGORY_INTERNET,
            help="""
Search and download web pages using Tavily.com search engine.
""",
        )

    def get_tools(self) -> list[Callable]:
        tools = super().get_tools()
        tools.extend(self.wrap_tool_functions([
                self.web_search_tool,
            ])
        )
        return tools

    async def web_search_tool(self,
                           query:          str,
                           include_images: bool = False) -> dict:
        """Returns a web search result pages and images using the Tavily search engine.
        """

        TAVILY_API_URL = "https://api.tavily.com"

        api_key: str|None = self.run_context.get_env_var("TAVILY_API_KEY") or config.get_tavily_api_key() 
        if api_key is None:
            return "Error: no API key available for the TAVILY API"

        max_results: int = 8
        """Max search results to return, default is 5"""
        search_depth: str = "advanced"
        '''The depth of the search. It can be "basic" or "advanced"'''
        include_domains: List[str] = []
        """A list of domains to specifically include in the search results. Default is None, which includes all domains."""
        exclude_domains: List[str] = []
        """A list of domains to specifically exclude from the search results. Default is None, which doesn't exclude any domains."""
        include_answer: bool = True
        """Include a short answer to original query in the search results. Default is False."""
        include_raw_content: bool = False
        """Include cleaned and parsed HTML of each site search results. Default is False."""

        params = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_domains": include_domains,
            "exclude_domains": exclude_domains,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
            "include_images": include_images,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TAVILY_API_URL}/search",
                json=params,
                timeout=90,
            )

        print(f"{TAVILY_API_URL}/search {response}")            
        response.raise_for_status()
        results = response.json()

        df = pd.DataFrame(results['results'])
        if 'images' in results:
            new_rows = pd.DataFrame({
            'url': results['images'],
            'title': ['image'] * len(results['images'])
        })

        # Concatenate the new rows to the existing DataFrame
        df = pd.concat([df, new_rows], ignore_index=True)

        return self.get_dataframe_preview(
            df, 
            max_rows=len(df),
            name_hint="tavily_results",
        )
    
    '''
        text_results = [f"search: {query}"]
        
        max_count = 10000 # need to know actual token limit
        used = len(text_results[-1])
        
        for result in results['results']: # Iterate over 'results' key which is a list of dictionaries

            text_results.append(f"{result['title']}: {result['url']}")
            used += len(text_results[-1])
            remaining = max_count - used
            
            if remaining > 0:
                text_results.append(result["content"])
            else:
                break
            
            used += len(text_results[-1])
            text_results.append("-----")
            
        return "\n".join(text_results)
    '''
