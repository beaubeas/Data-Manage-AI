from openai import AsyncOpenAI
import base64
from anthropic import AsyncAnthropic
import requests
import mimetypes
from typing import Optional
from PIL import Image
from io import BytesIO
from supercog.engine.tool_factory import ToolFactory, ToolCategory, LLMFullResult
from supercog.shared.services import config

from typing import Callable

class ImageAnalysisTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id = "image_analysis",
            system_name = "Image Analysis & Recognition",
            logo_url="/mag-glass-chart.png",
            auth_config = { },
            category=ToolCategory.CATEGORY_GENAI,
            help="""
Use LLM vision to analyze images
""",
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.analyze_image,
        ])
        
    async def chunk_image(self, image_data: bytes, max_height: int) -> list:
        """Splits the image into chunks of max_height pixels high."""
        image = Image.open(BytesIO(image_data))
        width, height = image.size
        print(f"Image dimensions: {width}x{height}")

        chunks = []
        for y in range(0, height, max_height):
            box = (0, y, width, min(y + max_height, height))
            chunk = image.crop(box)
            output = BytesIO()
            chunk.save(output, format="PNG")
            chunks.append(base64.b64encode(output.getvalue()).decode('utf-8'))
        return chunks
    
    async def analyze_image(self, query: str, image_url: str, max_images: Optional[int]=10, max_height = 1024, max_token = 512) -> str:
        """ Uses LLM to analyze the given image to answer the query. The image
            can either be a URL or a path to a local file. Always returns the full content of the analysis.
        """
        image_data = image_url
        if not image_url.startswith("http"):
            mime_type = mimetypes.guess_type(image_url)[0]
            print("Found mime type: ", mime_type)
            if not mime_type or not mime_type.startswith("image/"):
                return "Error, input file {image_url} is not an image"
            
            with open(image_url, "rb") as image_file:
                image_data = image_file.read()
            print(type(image_data))
            download_url: dict = self.run_context.get_file_url(image_url)
        else:
            download_url = {"url": image_url}
            try:
                response = requests.get(download_url)  
                response.raise_for_status()
                image_data = response.content
            except Exception as e:
                pass
        # Check image length and chunk if necessary
        image_chunks = await self.chunk_image(image_data, max_height)
        
        result=""

        if config.get_global("CLAUDE_INTERNAL_API_KEY"):    
            # content for CLAUDE Model
            client = AsyncAnthropic(api_key=config.get_global("CLAUDE_INTERNAL_API_KEY"))
            
            for encoded_chunk in image_chunks[:max_images]:
                message = await client.messages.create(  
                    model="claude-3-5-sonnet-20241022",  
                    max_tokens=max_token,  
                    messages=[  
                        {  
                            "role": "user",  
                            "content": [
                                {"type": "text", "text": query},
                                {
                                    "type": "image", 
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png", 
                                        "data": encoded_chunk
                                        }
                                }
                            ] 
                        }  
                    ],  
                )
                result += message.content[0].text
            return LLMFullResult(f"Show the image: ![{image_url}]({download_url})\n\n\n{result}")
        else:
            # content for GPT Model
            client = AsyncOpenAI(api_key=config.get_global("OPENAI_API_KEY"))
            
            for encoded_chunk in image_chunks[:max_images]:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": query},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_chunk}"}}
                        ]
                        }
                    ],
                    max_tokens=max_token,
                )
                result += response.choices[0].message.content
            return LLMFullResult(f"Show the image: ![{image_url}]({download_url})\n\n\n{result}")
