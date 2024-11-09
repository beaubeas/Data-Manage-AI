import json
import tempfile
from typing import Callable
from pathlib import Path
from openai import AsyncOpenAI
from io import BytesIO
from PIL import Image
import requests

from supercog.shared.services import db_connect, config
from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.utils import upload_file_to_s3
from supercog.engine.tools.s3_utils import public_image_bucket
from supercog.engine.filesystem import unrestricted_filesystem

class ImageGeneratorTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id = "image_generator",
            system_name = "Image Generator",
            help="""
Use Dall*e to generate an image from a description
""",
            logo_url=super().logo_from_domain("openai.com"),
            auth_config = { },
            category=ToolCategory.CATEGORY_GENAI
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([self.generate_image])
    
    async def generate_image(self, description: str) -> str:
        """ Generates an image from the description and returns the
            image url in Markdown syntax.
        """
        client = AsyncOpenAI(api_key=config.get_global("OPENAI_API_KEY"))

        print("GENERATING IMAGE, using desc:\n", description)
        response = await client.images.generate(
            #model="dall-e-3",
            prompt=description,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        with unrestricted_filesystem():
            image: Image.Image = download_image(image_url)

            image = fix_image(image)

            outfile = tempfile.NamedTemporaryFile(delete=False)
            image.save(outfile, format="PNG")
            outfile.close()
            public_url = upload_file_to_s3(
                outfile.name, 
                public_image_bucket(),
                mime_type="image/png"
            )

        return f"![Generated Image]({public_url})"

def download_image(url) -> Image.Image:
    r = requests.get(url)
    r.raise_for_status()

    return Image.open(BytesIO(r.content))

def fix_image(image: Image.Image):
    # Resize
    return image.resize((512,512))
