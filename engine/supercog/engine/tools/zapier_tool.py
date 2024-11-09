from supercog.engine.tool_factory import ToolFactory, ToolCategory, TOOL_REGISTRY
from supercog.shared.services import config
from typing import List, Callable, Dict, Any
import json
import requests

class ZapierTool(ToolFactory):
    base_url: str = "https://api.zapier.com/v2"

    def __init__(self):
        super().__init__(
            id="zapier_connector",
            system_name="Zapier",
            logo_url="https://logo.clearbit.com/zapier.com",
            category=ToolCategory.CATEGORY_SAAS,
            help="Use this tool to interact with Zapier and connected systems",
            auth_config={
                "strategy_token": {
                    "ZAPIER_API_KEY": "Your Zapier API Key",
                    "help": "Configure your Zapier API key to access Zapier services."
                }
            }
        )

    def get_tools(self) -> List[Callable]:
        """
        Wraps the tool functions
        :return: A list of callable functions that the tool provides.
        """
        return self.wrap_tool_functions([
            self.list_zaps,
            self.execute_zap,
            self.retrieve_data,
            self.write_data,
        ])

    def _get_headers(self) -> Dict[str, str]:
        """
        Retrieves the headers for API requests, including the API key from auth_config.
        
        :return: A dictionary of headers for API requests.
        """
        api_key = self.auth_config.get("strategy_token", {}).get("ZAPIER_API_KEY")
        if not api_key:
            raise ValueError("Zapier API key not found in auth_config")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def _handle_response(self, response: requests.Response, action: str) -> str:
        """
        Handles the API response and returns appropriate JSON string.
        
        :param response: The response object from the API call.
        :param action: The action being performed (e.g., "retrieve Zaps", "execute Zap").
        :return: A JSON string containing the result or error information.
        """
        if response.status_code == 200:
            return json.dumps(response.json(), indent=2)
        else:
            error_message = f"Failed to {action}. Status code: {response.status_code}"
            try:
                error_details = response.json()
            except json.JSONDecodeError:
                error_details = {"message": response.text}
            
            return json.dumps({
                "error": error_message,
                "details": error_details
            }, indent=2)

    def list_zaps(self) -> str:
        """
        Lists all available Zaps for the authenticated user.
        
        :return: A JSON string containing information about available Zaps or error details.
        """
        endpoint = f"{self.base_url}/zaps"
        headers = self._get_headers()
        
        try:
            response = requests.get(endpoint, headers=headers)
            return self._handle_response(response, "retrieve Zaps")
        except requests.RequestException as e:
            return json.dumps({"error": f"Failed to connect to Zapier API: {str(e)}"})

    def execute_zap(self, zap_id: str, input_data: Dict[str, Any]) -> str:
        """
        Executes a specific Zap with the given input data.
        
        :param zap_id: The ID of the Zap to execute.
        :param input_data: A dictionary containing the input data for the Zap.
        :return: A JSON string containing the result of the Zap execution or error details.
        """
        endpoint = f"{self.base_url}/zaps/{zap_id}/execute"
        headers = self._get_headers()
        
        try:
            response = requests.post(endpoint, headers=headers, json=input_data)
            return self._handle_response(response, f"execute Zap {zap_id}")
        except requests.RequestException as e:
            return json.dumps({"error": f"Failed to connect to Zapier API: {str(e)}"})

    def retrieve_data(self, zap_id: str, action_id: str, params: Dict[str, Any] = None) -> str:
        """
        Retrieves data from a connected system using a specific Zap action.
        
        :param zap_id: The ID of the Zap to use.
        :param action_id: The ID of the action within the Zap to execute.
        :param params: Optional parameters to pass to the action.
        :return: A JSON string containing the retrieved data or error details.
        """
        endpoint = f"{self.base_url}/zaps/{zap_id}/actions/{action_id}"
        headers = self._get_headers()
        
        try:
            response = requests.get(endpoint, headers=headers, params=params)
            return self._handle_response(response, f"retrieve data from Zap {zap_id}, action {action_id}")
        except requests.RequestException as e:
            return json.dumps({"error": f"Failed to connect to Zapier API: {str(e)}"})

    def write_data(self, zap_id: str, action_id: str, data: Dict[str, Any]) -> str:
        """
        Writes data to a connected system using a specific Zap action.
        
        :param zap_id: The ID of the Zap to use.
        :param action_id: The ID of the action within the Zap to execute.
        :param data: The data to write to the connected system.
        :return: A JSON string containing the result of the write operation or error details.
        """
        endpoint = f"{self.base_url}/zaps/{zap_id}/actions/{action_id}"
        headers = self._get_headers()
        
        try:
            response = requests.post(endpoint, headers=headers, json=data)
            return self._handle_response(response, f"write data to Zap {zap_id}, action {action_id}")
        except requests.RequestException as e:
            return json.dumps({"error": f"Failed to connect to Zapier API: {str(e)}"})
