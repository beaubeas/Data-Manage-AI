from typing import Callable, Optional

from ..tool_factory import ToolFactory, ToolCategory
from .rest_tool_v2 import RESTAPIToolV2

class AuthorizedRESTAPITool(RESTAPIToolV2):
    def __init__(self):
        super().__init__(
            id="auth_rest_api_tool",
            system_name="REST API (Authorized)",
            logo_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQHWEG81eOfB0EdeEeaDC9R-cn7BRpc3ctI9g&s",
            category=ToolCategory.CATEGORY_DEVTOOLS,
            tool_uses_env_vars=False, # auth is configured via Connection
            auth_config={
                "strategy_token": {
                    "bearer_token": "Bearer token (or env var) for auth",
                    "bearer_token_name": "Name of the token (default is 'Bearer')",
                    "basic_username": "For Basic auth, the username (or env var)",
                    "basic_password": "For Basic auth, the password (or env var)",
                    "request_arg_name": "Name of the auth request parameter",
                    "request_arg_value": "Value or env var for the arg value",
                    "header_name": "Name of the auth header",
                    "header_value": "Value or env var for the header value",
                }
            },
            help="""
Call REST API endpoints with authorization. Specify values according to the type of auth required and leave the rest blank.
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.add_request_header,
            self.get_resource,
            self.post_resource,
            self.put_resource,
            self.patch_resource,
            self.delete_resource,
            self.debug_request,
        ])

    def test_credential(self, cred, secrets: dict) -> str|None:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """
        msgs = []
        if secrets.get("bearer_token"):
            valid, msg = self.run_context.validate_secret(secrets.get("bearer_token"))
            if not valid:
                msgs.append(msg)
        elif secrets.get("basic_username"):
            valid, msg = self.run_context.validate_secret(secrets.get("basic_username"))
            if not valid:
                msgs.append(msg)
            valid, msg = self.run_context.validate_secret(secrets.get("basic_password"))
            if not valid:
                msgs.append(msg)
        elif secrets.get("request_arg_name"):
            valid, msg = self.run_context.validate_secret(secrets.get("request_arg_value"))
            if not valid:
                msgs.append(msg)
        elif secrets.get("header_name"):
            valid, msg = self.run_context.validate_secret(secrets.get("header_value"))
            if not valid:
                msgs.append(msg)
        return "\n".join(msgs) if len(msgs) > 0 else None


    async def get_auth_variable(self):
        auth_type = "none"
        if self.credentials.get("bearer_token"):
            auth_type = "bearer"
        elif self.credentials.get("basic_username"):
            auth_type = "basic"
        elif self.credentials.get("request_arg_name"):
            auth_type = "argument"
        
        auth_var = await super().prepare_auth_config(
            auth_type=auth_type,
            username=self.credentials.get("basic_username"), 
            password=self.credentials.get("basic_username"), 
            token=self.credentials.get("bearer_token") or self.credentials.get("request_arg_value"),
            token_name=self.credentials.get("bearer_token_name") or "Bearer",
        )

        if self.credentials.get("header_name"):
            super().add_request_header(auth_var, self.credentials.get("header_name"), self.credentials.get("header_value"))

        return auth_var

    async def get_resource(
            self, 
            url: str, 
            params: dict = {},
        ):
        """ Invoke the GET REST endpoint on the indicated URL, using authentication already configured.
            returns: the JSON response, or the response text and status code.
        """
        return await super().get_resource(url, params, auth_config_var=await self.get_auth_variable())

    async def post_resource(
            self, 
            url: str, 
            content_type: str = "application/json",
            data: str = "{}",
        ):
        """ Invoke the POST REST endpoint, using authentication already configured. 
            Supply a data dictionary of params (as json data). The data will be submitted
            as json or as form data (application/x-www-form-urlencoded).
            Returns the response and status code. 
        """
        return await super().post_resource(url, content_type, data, auth_config_var=await self.get_auth_variable())

    async def put_resource(
            self, 
            url: str, 
            data: str = "{}",
        ):
        """ Invoke the PUT REST endpoint. 
            Supply a data dictionary of params (as json data). 
        """
        return await super().put_resource(url, data, auth_config_var=await self.get_auth_variable())

    async def patch_resource(
            self, 
            url: str, 
            data: str = "{}",
        ):
        """ Invoke the PATCH REST endpoint.
            Supply a data dictionary of params (as json data). 
        """
        return await super().patch_resource(url, data, auth_config_var=await self.get_auth_variable())


    async def delete_resource(
            self, 
            url: str,
    ):
        """ Invoke the DELETE REST endpoint. """
        return await super().delete_resource(url, auth_config_var=await self.get_auth_variable())
