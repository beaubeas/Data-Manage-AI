import json
import requests
import re
from typing import Callable, List, Dict, Optional, Union, Tuple
from supercog.engine.tool_factory import ToolFactory, ToolCategory
from pydantic import BaseModel, Field
from openai import OpenAI
from supercog.shared.services import config

MODEL_NAME = "gpt-4o-mini"

class SwaggerTool(ToolFactory, BaseModel):
    swagger_data: Optional[Dict] = Field(default=None)
    _client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))
        return self._client

    def __init__(self, **data):
        super().__init__(
            id="swagger_tool",
            system_name="Swagger API Tool",
            help="Retrieve and process Swagger API documentation for constructing network requests.",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/a/ab/Swagger-logo.png",
            category=ToolCategory.CATEGORY_DEVTOOLS,
            auth_config = {},
            **data
        )

    def get_tools(self) -> List[Callable]:
        # Return a list of wrapped tool functions
        return self.wrap_tool_functions([
            self.load_swagger_documentation,
            self.find_swagger_documentation_for_request,
            self.list_api_endpoints,
            self.get_api_request_data
        ])

    def load_swagger_documentation(self, url: str):
        """
        Loads and processes Swagger API documentation from a given URL.
        
        :param url: URL of the Swagger JSON
        """
        print("Loading Swagger documentation...")
        self.swagger_data = SwaggerUtil.fetch_swagger_data(url)
        if self.swagger_data:
            return f"Successfully loaded Swagger documentation with {len(self.swagger_data.get('paths', {}))} endpoints."
        else:
            return "Failed to load Swagger documentation."
    
    def find_swagger_documentation_for_request(self, search: str):
        """
        Find the most relevant API endpoint for a given search query.

        Args:
            search (str): Search query describing desired API functionality.

        Returns:
            dict: Matching endpoint data or error message.
        """
        if not self.swagger_data:
            return "No Swagger documentation loaded. Please load the documentation first."

        endpoints = list(self.swagger_data['paths'].keys())
        prompt = f"Given the following API endpoints:\n\n{', '.join(endpoints)}\n\nWhich endpoint is most relevant for the search: '{search}'? Return only the exact endpoint key."

        response = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that finds the most relevant API endpoint based on a search query."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "text"},
        )

        selected_endpoint = response.choices[0].message.content.strip()
        print("selected_endpoint", selected_endpoint)

        if selected_endpoint in self.swagger_data['paths']:
            return self.swagger_data['paths'][selected_endpoint]
        else:
            return f"No matching endpoint found for '{search}'"

    def list_api_endpoints(self):
        """
        Lists all available API endpoints from the loaded Swagger documentation.
        
        :return: List of API endpoints
        """
        if self.swagger_data is None or 'paths' not in self.swagger_data:
            return []
        return list(self.swagger_data['paths'].keys())

    def get_api_request_data(self, path_key: str):
        """
        Retrieves detailed request data for a specific API endpoint.
        
        :param path_key: The path key in the format "METHOD /path"
        :return: Request info
        """
        if self.swagger_data is None:
            return None
        
        merged_data = SwaggerUtil.merge_path_with_schema(self.swagger_data, path_key)
        return merged_data


class SwaggerUtil:
    @staticmethod
    def fetch_swagger_json(url):
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching data from URL: {e}")
            return None

    @staticmethod
    def remove_responses(obj):
        if isinstance(obj, dict):
            return {k: SwaggerUtil.remove_responses(v) for k, v in obj.items() if k != 'responses'}
        elif isinstance(obj, list):
            return [SwaggerUtil.remove_responses(item) for item in obj]
        else:
            return obj

    @classmethod
    def extract_paths_and_schemas(cls, swagger_data):
        paths = swagger_data.get('paths', {})
        components = swagger_data.get('components', {})
        schemas = components.get('schemas', {})

        extracted_paths = {}
        for path, methods in paths.items():
            for method, details in methods.items():
                endpoint_key = f"{method.upper()} {path}"
                filtered_details = cls.remove_responses(details)
                
                extracted_paths[endpoint_key] = {
                    "name": path,
                    "data": {
                        method: filtered_details
                    }
                }

        cleaned_schemas = cls.remove_responses(schemas)

        return extracted_paths, cleaned_schemas

    @classmethod
    def fetch_swagger_data(cls, url):
        swagger_data = cls.fetch_swagger_json(url)
        if swagger_data:
            paths, schemas = cls.extract_paths_and_schemas(swagger_data)
            return {
                "paths": paths,
                "schemas": schemas
            }
        return None

    @staticmethod
    def merge_path_with_schema(data, path_key):
        path_data = data["paths"].get(path_key)
        if not path_data:
            return None

        method_data = next(iter(path_data["data"].values()))
        request_body = method_data.get("requestBody")
        if not request_body:
            return path_data

        content = request_body.get("content", {})
        schema_ref = None
        for content_type in ["application/json", "text/json", "application/*+json"]:
            if content_type in content:
                schema_ref = content[content_type].get("schema", {}).get("$ref")
                break

        if not schema_ref:
            return path_data

        schema_name = re.search(r'#/components/schemas/(\w+)', schema_ref)
        if not schema_name:
            return path_data

        schema_name = schema_name.group(1)
        schema = data["schemas"].get(schema_name)
        if not schema:
            return path_data

        merged_data = path_data.copy()
        merged_data["requestBody"] = schema
        merged_data['content'] = "application/json"
        # Remove requestBody from the merged data
        if "requestBody" in merged_data["data"][next(iter(merged_data["data"]))]:
            del merged_data["data"][next(iter(merged_data["data"]))]["requestBody"]

        return merged_data