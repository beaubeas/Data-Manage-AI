import re
from openai import AsyncOpenAI

#from openai import OpenAI
from sqlmodel import Session
from io import BytesIO

from PIL import Image
import requests

from supercog.shared.services import db_connect, config
from .models import Agent

async def generate_agent_image(service:str, agent_id: str, name: str, description: str):
    client = AsyncOpenAI(api_key=config.get_global("OPENAI_API_KEY"))

    crop_image = False
    prompt = description

    quality = "standard"
    # let super users adjust quality
    m = re.search(r"Quality:\s*([^\s]+)", description)
    if m:
        quality = m.group(1)

    print(f"Quality is {quality}")
    print("GENERATING AVATAR IMAGE, using desc:\n", prompt)
    try:
        # Test description just contains a URL
        if re.match(r"^https?://", description):
            image_url = description
        else:
            response = await client.images.generate(
                #model="dall-e-3",
                #model="gpt-4o",
                prompt=prompt,
                size="512x512",
                quality=quality,
                n=1,
            )
            image_url = response.data[0].url
        
        image: Image.Image = download_image(image_url)

        if crop_image:
            image = fix_image(image)

        with Session(db_connect(service)) as sess:
            agent = sess.get(Agent, agent_id)
            if agent:
                agent.avatar_url = image_url
                bytes_buffer = BytesIO()
                image.save(bytes_buffer, format="PNG")
                agent.avatar_blob = bytes_buffer.getvalue()
                agent.upload_image_to_s3()
                agent.avatar_blob = b''
                sess.add(agent)
                sess.commit()
                print("Agent avatar_blob was updated")
            else:
                raise ValueError("No agent found")
    except Exception as e:
        print(f"Error generating image: {str(e)}")
        raise  # Re-raise the exception to be caught by the calling function

def download_image(url) -> Image.Image:
    try:
        r = requests.get(url)
        r.raise_for_status()
        return Image.open(BytesIO(r.content))
    except requests.RequestException as e:
        raise ValueError(f"Failed to download image: {str(e)}")

def fix_image(image: Image.Image):
    width, height = image.size

    # Calculate the dimensions to crop
    new_width = width * 0.2
    new_height = height * 0.2

    # Calculate the points for the cropping box
    left = new_width
    upper = new_height
    right = width - new_width
    lower = height - new_height

    # Crop the image
    cropped_image = image.crop((left, upper, right, lower))

    # Resize
    return cropped_image.resize((64,64))
