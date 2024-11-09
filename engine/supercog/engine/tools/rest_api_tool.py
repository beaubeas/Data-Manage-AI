import asyncio
from typing import Callable, Any, Optional
import requests
from io import BytesIO
from PIL import Image
import boto3
import tempfile
import uuid
import pandas as pd
import aiohttp
import aiofiles
from aiohttp import FormData
import pandas as pd
import math
import numpy as np

from langchain.agents import tool

from supercog.engine.tool_factory import (
    ToolFactory, 
    ToolCategory, 
    LangChainCallback,
)
from supercog.shared.utils import upload_file_to_s3
from supercog.engine.tools.s3_utils import public_image_bucket

class RESTAPITool(ToolFactory):
    return_dataframe: bool=False
    def __init__(self):
        super().__init__(
            id="rest_api_tool",
            system_name="REST API",
            auth_config={},
            logo_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQHWEG81eOfB0EdeEeaDC9R-cn7BRpc3ctI9g&s",
            category=ToolCategory.CATEGORY_DEVTOOLS,
            tool_uses_env_vars=True,
            help="""
Call any REST API endpoints.
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.call_rest_endpoint,
        ])
    
    async def call_rest_endpoint(
        self,
        endpoint_url:     str,
        method:           str = "GET",
        params:           dict = {},
        headers:          dict = {},
        basic_auth:       list = [],
        param_auth:       dict = {},
        post_mime_type:   str = "application/json",
        file_path:        str = None,
        form_data:        dict = None,
        return_dataframe: bool=False,
        delay:            float = 0, 
        callbacks:        LangChainCallback = None,
    ):
        """ Invoke a REST API endpoint. Supports JSON data and form data with file uploads.
            Supply 'GET' or 'POST' for the method, and a dictionary of params(as json data).
            You can supply authentication as either 
            Basic Authentication: ["username", "password"] or
            an API parameter: {"key":"value"}. Any param or header can refer to
            ENV VARS using ${KEY} syntax.
            For file uploads, provide the file_path and set post_mime_type to "multipart/form-data".
            The 'delay' parameter allows you to specify a delay in seconds before making the API call.
        """
        if delay > 0:
            print("Sleeping for", delay, "seconds before making the API call.")
            await asyncio.sleep(delay)
        
        self.return_dataframe = return_dataframe
        await self.log(f"Calling REST API endpoint: {endpoint_url}", callbacks)

        auth = None
        if basic_auth:
            if len(basic_auth) == 1:
                basic_auth.append("")
            if isinstance(basic_auth[0], dict):
                basic_auth[0] = list(basic_auth[0].values())[0]
            if isinstance(basic_auth[1], dict):
                basic_auth[1] = list(basic_auth[1].values())[0]
            auth = aiohttp.BasicAuth(
                self.run_context.resolve_secrets(basic_auth[0]), 
                self.run_context.resolve_secrets(basic_auth[1])
            )
        if param_auth:
            params.update(param_auth)
            
        timeout      = aiohttp.ClientTimeout(total=60)  # 60 seconds timeout
        params       = self.run_context.resolve_secret_values(values=params)
        headers      = self.run_context.resolve_secret_values(values=headers)
        endpoint_url = self.run_context.resolve_secrets(endpoint_url)

        async with aiohttp.ClientSession(auth=auth, timeout=timeout) as session:
            if method == "GET":
                async with session.get(endpoint_url, params=params, headers=headers) as response:
                    return await self.process_response(response)
            elif method == "POST":
                if post_mime_type == "application/json":
                    async with session.post(endpoint_url, json=params, headers=headers) as response:
                        return await self.process_response(response)
                elif post_mime_type == "multipart/form-data":
                    form = FormData()
                    if form_data:
                        for key, value in form_data.items():
                            form.add_field(key, str(value))
                    if file_path:
                        async with aiofiles.open(file_path, 'rb') as f:
                            form.add_field('file', f, filename=file_path.split('/')[-1])
                    async with session.post(endpoint_url, data=form, headers=headers) as response:
                        return await self.process_response(response)
                else:
                    async with session.post(endpoint_url, data=params, headers=headers) as response:
                        return await self.process_response(response)
            else:
                return f"Error: Unsupported method '{method}'"

    async def process_response(self, response):
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            return await     self.process_json(response)
        elif 'image'                in content_type:
            return await     self.process_image(response)
        elif 'text/html'            in content_type:
            return {"html": await response.text()}
        elif 'text/plain'           in content_type:
            return {"text": await response.text()}
        elif 'text/csv'             in content_type:
            return {"csv":  await response.text()}
        elif 'application/atom+xml' in content_type:
            return {"xml":  await response.text()}
        else:
            return "Error: Unsupported response content type '{}'".format(content_type)

    async def process_json(self,response, ):
        json = await response.json()
        #json = self.clean_json_data(json)
        if not self.return_dataframe:
            return json
        else:
            df = pd.json_normalize(json)
            df.replace({np.nan: ''}, inplace=True)
            return self.get_dataframe_preview(df)
        
    def clean_json_data(self,data):
        if isinstance(data, dict):
            return {k: self.clean_json_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.clean_json_data(v) for v in data]
        elif isinstance(data, float) and math.isnan(data):
            return None  # or a default value like 0
        else:
            return data
        
    async def process_image(self, response):
        """
        Image Formats Supported
        BMP
        EPS
        GIF
        ICNS
        ICO
        IM
        JPEG      .jpg
        JPEG 2000
        MSP
        PCX
        PNG       .png
        PPM
        SGI
        SPIDER
        TIFF
        WebP
        XBM
        XV
        """
        format= "PNG"
        extension = "png"
        
        print(f"***************> Got an image to return:")
        # Read the image data as bytes
        image_data = await response.read()  # Read the image data as bytes
        image = Image.open(BytesIO(image_data))

        # Convert RGBA to RGB if necessary
        if format == "JPEG":
            if image.mode == "RGBA":
                image = image.convert("RGB")
            
        # Create an in-memory bytes buffer to save the image
        image_buffer = BytesIO()
        image.save(image_buffer, format=format)
        image_buffer.seek(0)  # Rewind the buffer to the beginning

        # Generate a unique object name for the S3 upload
        object_name = f"images/{uuid.uuid4()}.{extension}"

        # Upload the image file to S3 and get the public URL
        public_url = upload_file_to_s3(
            image_buffer, 
            public_image_bucket(), 
            object_name, 
            mime_type=f"image/{extension}"
        )

        # Return markdown formatted image link
        return {"thumb": f"![Generated Image]({public_url})"}
        
