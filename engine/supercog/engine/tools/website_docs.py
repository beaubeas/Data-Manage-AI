from typing import AsyncGenerator, Optional
from firecrawl import FirecrawlApp
import requests
from ragie import Ragie

from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.engine.doc_source_factory import DocSourceFactory
from supercog.shared.services import config
from supercog.engine.rag_utils import get_user_personal_index, get_ragie_partition
from supercog.engine.jwt_auth import User

class WebsiteDocSource(DocSourceFactory):
    def __init__(self):
        super().__init__(
            id="website_file_source",
            system_name="Website Documents",
            logo_url=super().logo_from_domain("firecrawl.com"),
            category=ToolCategory.CATEGORY_DOCSRC,
            auth_config={
                "strategy_token": {
                    "url": "Website URL to parse",
                },
            },
            help="""
Load and index documents from websites using Firecrawl for parsing.
"""
        )

    async def get_documents(
            self, 
            url: str = None, 
            tenant_id: str = None, 
            index_id: str = None,
            **kwargs,
        ) -> AsyncGenerator[str, None]:
        """Yields parsed content from the webpage."""
        try:
            # Use URL from credentials if not provided as parameter
            url = url or self.credentials.get("url")
            if not url:
                raise ValueError("No URL provided")
                
            print(f"Crawling site: {url}")

            # Use Firecrawl to crawl the website
            api_key = config.get_global("FIRECRAWL_API_KEY", required=False)
            if not api_key:
                raise ValueError("Firecrawl API key not found in global config")
            
            firecrawl = FirecrawlApp(api_key=api_key)
            crawl_response = firecrawl.crawl_url(
                url,
                params={
                    'limit': 20,  # Default max pages
                    'scrapeOptions': {
                        'formats': ['markdown']
                    }
                },
                poll_interval=30
            )

            if not crawl_response or not isinstance(crawl_response, dict):
                raise ValueError(f"Unexpected response from Firecrawl for URL: {url}")

            # Check if the crawl was successful
            if crawl_response.get('status') != 'completed':
                raise ValueError(f"Crawl not completed. Status: {crawl_response.get('status')}")

            # Get the crawled data
            crawl_data = crawl_response.get('data', [])
            if not crawl_data:
                raise ValueError(f"No content found on the website: {url}")

            # Initialize Ragie client
            ragie = Ragie(auth=config.get_global('RAGIE_API_KEY', required=False) or "")
            partition = get_ragie_partition(tenant_id, index_id)

            # Process each page
            for page in crawl_data:
                if isinstance(page, dict) and 'markdown' in page and page['markdown'].strip():
                    content = page['markdown']
                    page_url = page.get('metadata', {}).get('sourceURL', url)
                    
                    # Send content to Ragie for indexing
                    response = ragie.documents.create_raw(
                        request={
                            "data": content,
                            "partition": partition,
                            "metadata": {
                                "source_url": page_url,
                                "source_type": "website"
                            }
                        }
                    )
                    print(f"Successfully indexed content from {page_url} to personal index")
                    yield content

        except Exception as e:
            print(f"Error processing webpage: {str(e)}")
            raise
