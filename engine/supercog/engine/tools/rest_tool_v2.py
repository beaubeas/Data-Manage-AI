from typing import Callable, Any, Optional, Dict, Awaitable, Union
from io import BytesIO
from PIL import Image
import requests
import uuid
import pandas as pd
import os
import json
from aiohttp import FormData
import pandas as pd
import math
import numpy as np
import random
from urllib.parse import urlparse
from pydantic import BaseModel

from urllib.parse import parse_qsl, urlencode

from supercog.engine.tool_factory import (
    ToolFactory, 
    ToolCategory, 
    LangChainCallback,
)
from supercog.shared.utils import upload_file_to_s3
from supercog.engine.tools.s3_utils import public_image_bucket

import os
from urllib.parse import urlparse
from typing import Dict, Optional, Any

from httpx import BasicAuth
import httpx

# Converted from requests lib to async httpx
# class RequestBuilder:
#     def __init__(self, base_url: str, logger_func: Callable[..., Awaitable[None]]):
#         parsed_url = urlparse(base_url)
#         self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
#         self.base_path = parsed_url.path
#         self.headers: Dict[str, str] = {}
#         self.auth: Optional[HTTPBasicAuth] = None
#         self.session: Optional[requests.Session] = None
#         self.logger_func = logger_func

#     def with_bearer_token(self, token: str, token_name: str = "Bearer"):
#         self.headers["Authorization"] = f"{token_name} {token}"
#         return self

#     def with_basic_auth(self, username: str, password: str):
#         self.auth = HTTPBasicAuth(username, password)
#         return self

#     def with_header(self, key: str, value: str):
#         self.headers[key] = value
#         return self

#     def create_session(self):
#         if self.session is None:
#             self.session = requests.Session()
#             self.session.headers.update(self.headers)
#             if self.auth:
#                 self.session.auth = self.auth

#     def close_session(self):
#         if self.session:
#             self.session.close()
#             self.session = None

#     def _ensure_session(self):
#         if self.session is None:
#             self.create_session()

#     async def _request(self, method: str, path: str, **kwargs) -> requests.Response:
#         self._ensure_session()
#         if self.base_url:
#             parsed = urlparse(path)
#             url = path if parsed.netloc else self.base_url + os.path.join(self.base_path, path).rstrip("/")
#         else:
#             url = path
#         await self.logger_func(f"{method.upper()} {url}")
#         if self.auth:
#             await self.logger_func(f"Auth: {self.auth.username}")
#         if self.headers:
#             await self.logger_func(f"--Headers--")
#             for k, v in self.headers.items():
#                 await self.logger_func(f"  {k}: {v}")
#         print(f"Requesting {method} {url}")
#         return self.session.request(method, url, timeout=60, **kwargs)

#     async def get(self, path: str, **kwargs):
#         return await self._request("GET", path, **kwargs)

#     async def post_json(self, path: str, json: Any = None, **kwargs):
#         return await self._request("POST", path, json=json, **kwargs)

#     async def put_json(self, path: str, json: Any = None, **kwargs):
#         return await self._request("PUT", path, json=json, **kwargs)

#     async def post_form(self, path: str, form_data: Any = None, **kwargs):
#         kwargs['data'] = form_data
#         kwargs.setdefault('headers', {})['Content-Type'] = 'application/x-www-form-urlencoded'
#         return await self._request("POST", path, **kwargs)

#     async def put(self, path: str, data: Any = None, json: Any = None, **kwargs):
#         return await self._request("PUT", path, data=data, json=json, **kwargs)

#     async def patch(self, path: str, data: Any = None, json: Any = None, **kwargs):
#         return await self._request("PATCH", path, data=data, json=json, **kwargs)

#     async def delete(self, path: str, **kwargs):
#         return await self._request("DELETE", path, **kwargs)


class AsyncRequestBuilder:
    def __init__(self, base_url: str, logger_func: Callable[..., Awaitable[None]]):
        parsed_url = urlparse(base_url)
        self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        self.base_path = parsed_url.path
        self.headers: Dict[str, str] = {}
        self.auth: Optional[BasicAuth] = None
        self.client: Optional[httpx.AsyncClient] = None
        self.logger_func = logger_func

    def with_bearer_token(self, token: str, token_name: str = "Bearer"):
        self.headers["Authorization"] = f"{token_name} {token}"
        return self

    def with_basic_auth(self, username: str, password: str):
        self.auth = BasicAuth(username, password)
        return self

    def with_header(self, key: str, value: str):
        self.headers[key] = value
        return self

    async def create_client(self):
        if self.client is None:
            self.client = httpx.AsyncClient(headers=self.headers, auth=self.auth)

    async def close_client(self):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _ensure_client(self):
        if self.client is None:
            await self.create_client()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        await self._ensure_client()
        if self.base_url:
            parsed = urlparse(path)
            url = path if parsed.netloc else self.base_url + os.path.join(self.base_path, path).rstrip("/")
        else:
            url = path
        await self.logger_func(f"{method.upper()} {url}")
        if self.auth:
            await self.logger_func(f"Auth: {self.auth}")
        if self.headers:
            await self.logger_func(f"--Headers--")
            for k, v in self.headers.items():
                await self.logger_func(f"  {k}: {v}")
        print(f"Requesting {method} {url}")
        return await self.client.request(method, url, timeout=60.0, **kwargs)

    async def get(self, path: str, **kwargs):
        return await self._request("GET", path, **kwargs)

    async def post_json(self, path: str, json: Any = None, **kwargs):
        return await self._request("POST", path, json=json, **kwargs)

    async def put_json(self, path: str, json: Any = None, **kwargs):
        return await self._request("PUT", path, json=json, **kwargs)

    async def post_form(self, path: str, form_data: Any = None, **kwargs):
        kwargs['data'] = form_data
        kwargs.setdefault('headers', {})['Content-Type'] = 'application/x-www-form-urlencoded'
        return await self._request("POST", path, **kwargs)

    async def put(self, path: str, data: Any = None, json: Any = None, **kwargs):
        return await self._request("PUT", path, data=data, json=json, **kwargs)

    async def patch(self, path: str, data: Any = None, json: Any = None, **kwargs):
        return await self._request("PATCH", path, data=data, json=json, **kwargs)

    async def delete(self, path: str, **kwargs):
        return await self._request("DELETE", path, **kwargs)

class RESTAPIToolV2(ToolFactory):
    request_map: dict[str, AsyncRequestBuilder] = {}
    return_dataframe: bool = False

    def __init__(self, **kwargs):
        if kwargs:
            super().__init__(**kwargs) # let people inherit from us to define new tools
        else:
            super().__init__(
                id="rest_api_tool_v2",
                system_name="REST API",
                auth_config={},
                logo_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQHWEG81eOfB0EdeEeaDC9R-cn7BRpc3ctI9g&s",
                category=ToolCategory.CATEGORY_DEVTOOLS,
                tool_uses_env_vars=True,
                help="""
    Call arbitrary REST API endpoints.
    """
            )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.prepare_auth_config,
            self.add_request_header,
            self.get_resource,
            self.post_resource,
            self.put_resource,
            self.patch_resource,
            self.delete_resource,
            self.debug_request,
        ])

    def debug_request(self, request_name: str):
        """ Returns debug information about the indicated request object. """
        request = self.request_map.get(request_name)
        if request is None:
            raise ValueError(f"Request '{request_name}' not found.")
        
        auth = ""
        if request.auth:
            auth = f"Auth: {request.auth}\n"

        res = f"""
        Base URL: {request.base_url}
        Headers: {request.headers}
        {auth}
        """
        return res

    async def prepare_auth_config(
            self, 
            auth_type: str, 
            username:str|None=None, 
            password:str|None=None, 
            token:str|None=None,
            token_name: str="Bearer"):
        """ Constructs an auth_config object to use with later requests. 
            auth_type is one of: basic, bearer, token
            For "basic" provide the username and password.
            For "bearer" provide the token.
            You can override the default "Bearer" token name.
            Any value can refer to ENV VARS using ${KEY} syntax.
            Returns the variable name of the auth config for use in request calls.
        """
        request = AsyncRequestBuilder("", logger_func=self.log)

        auth_type = auth_type.lower()

        if auth_type == "basic":
            username = self.run_context.resolve_secrets(username or "")
            password = self.run_context.resolve_secrets(password or "")
            request = request.with_basic_auth(username, password)
            await self.log("Basic Auth: {} / {}".format(username, password))
        elif auth_type in ["bearer", "token"]:
            token = self.run_context.resolve_secrets(token or "")
            request = request.with_bearer_token(token, token_name)
            await self.log(f"[token] {token_name}: {token}")
        elif auth_type == "none":
            pass
        else:
            raise ValueError(f"Unsupported auth type: {auth_type}")
        
        name = f"auth_{random.randint(1000,9999)}"
        self.request_map[name] = request
        return name

    def add_request_header(self, auth_config_var: str, name: str, value: str) -> str:
        """ Add a header to the auth config which was created already. """
        request = self.request_map.get(auth_config_var)
        if request is None:
            raise ValueError(f"Request '{auth_config_var}' not found.")
        
        request.headers[name] = value
        return "OK"
    
    async def get_resource(
            self, 
            url: str, 
            params: dict = {},
            auth_config_var: Optional[str]="", 
        ):
        """ Invoke the GET REST endpoint on the indicate URL. If the endpoints requires
            authentication then call 'prepare_auth_config' first and pass the config name to this function.
            returns: the JSON response, or the response text and status code.
        """
        if auth_config_var:
            request = self.request_map.get(auth_config_var)
            if request is None:
                raise ValueError(f"Auth config '{auth_config_var}' not found. Must call prepare_auth_config first.")
        else:
            request = AsyncRequestBuilder("", logger_func=self.log)

        response = await request.get(url, params=params)
        
        return await self.process_response(response)

    async def _post_json(
            self,
            auth_config_var: str|None,
            url: str, 
            params: dict|str,
            method="POST",
    ):
        if isinstance(params, str):
            params = json.loads(params)

        if not auth_config_var:
            request = AsyncRequestBuilder("", logger_func=self.log)
        else:
            request = self.request_map.get(auth_config_var)
            if request is None:
                raise ValueError(f"Request '{auth_config_var}' not found.")

        response = await request._request(method, url, json=params)
        return response
        


    async def post_resource(
        self, 
        path: str, 
        content_type: str = "application/json",
        data: Union[str, dict] = "{}",
        auth_config_var: Optional[str] = "",
    ):
        """ Invoke the POST REST endpoint. Pass an auth config name if the request needs authentication. 
            Supply data as a string or dictionary. For JSON, use a JSON-formatted string or a dictionary.
            For form data, use a dictionary or URL-encoded string.
            Returns the response and status code. 
        """
        # Convert data to a dictionary if it's a string
        if isinstance(data, str):
            try:
                params = json.loads(data)
            except json.JSONDecodeError:
                # If JSON decoding fails, assume it's URL-encoded form data
                params = dict(parse_qsl(data))
        else:
            params = data

        if content_type == "application/json":
            response = await self._post_json(auth_config_var or "", path, params, "POST")
        else:
            if auth_config_var:
                request = self.request_map.get(auth_config_var)
                if request is None:
                    raise ValueError(f"Request '{auth_config_var}' not found.")
            else:
                request = AsyncRequestBuilder("", logger_func=self.log)

            # Convert params to URL-encoded string if it's not already
            if isinstance(params, dict):
                form_data = urlencode(params)
            else:
                form_data = params

            response = await request.post_form(path, form_data=form_data)

        return await self.process_response(response)

    async def put_resource(
            self, 
            url: str, 
            data: str = "{}",
            auth_config_var: Optional[str]="",
        ):
        """ Invoke the PUT REST endpoint using the prepared request object. 
            Supply a data dictionary of params (as json data). 
        """
        response = await self._post_json(auth_config_var, url, data, method="PUT")

        return await self.process_response(response)

    async def patch_resource(
            self, 
            url: str, 
            data: str = "{}",
            auth_config_var: Optional[str]="",
        ):
        """ Invoke the PATCH REST endpoint using the prepared request object. 
            Supply a data dictionary of params (as json data). 
        """
        response = await self._post_json(auth_config_var, url, data, method="PATCH")

        return await self.process_response(response)


    async def delete_resource(
            self, 
            url: str,
            auth_config_var: Optional[str]="",
    ):
        """ Invoke the DELETE REST endpoint using the prepared request object. """
        if auth_config_var:
            request = self.request_map.get(auth_config_var)
            if request is None:
                raise ValueError(f"Request '{auth_config_var}' not found.")
        else:
            request = AsyncRequestBuilder("", logger_func=self.log)

        response = await request.delete(url)
        return await self.process_response(response)
    
###################

    async def process_response(self, response: httpx.Response):
        if response.status_code >= 400:
            return {"status": response.status_code, "response": str(response), "text": response.text}
        
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            return await     self.process_json(response)
        elif 'image'                in content_type:
            return await     self.process_image(response)
        elif 'text/html'            in content_type:
            return {"html": response.text}
        elif 'text/plain'           in content_type:
            return {"text": response.text}
        elif 'text/csv'             in content_type:
            return {"csv":  response.text}
        elif 'application/atom+xml' in content_type:
            return {"xml":  response.text}
        else:
            return "Error: Unsupported response content type '{}'".format(content_type)


    async def process_json(self, response: httpx.Response):
        json = response.json()
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
        
    async def process_image(self, response: httpx.Response):
        return await RESTAPIToolV2._process_image(response.content)  # Read the image data as bytes

    @staticmethod
    async def _process_image(image_data: bytes):
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
        
