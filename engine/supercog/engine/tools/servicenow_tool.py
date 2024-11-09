from supercog.engine.tool_factory import ToolFactory, ToolCategory
from typing import List, Callable, Optional, Dict, Any
import json
import requests
from datetime import datetime
from pydantic import Field


class ServiceNowCustomTool(ToolFactory):
    session: Optional[requests.Session] = Field(default=None, exclude=True)
    instance_url: Optional[str] = Field(default=None)
    
    def __init__(self, **kwargs):
        auth_config = {
            "servicenow_credentials": {
                "instance_url": "Your ServiceNow instance URL (e.g., https://your-instance.service-now.com)",
                "username": "Your ServiceNow username",
                "password": "Your ServiceNow password",
                "help": """
Please provide your ServiceNow instance URL, username, and password. 
These credentials will be used to authenticate with your ServiceNow instance.
"""
            }
        }

        super().__init__(
            id="servicenow_custom_connector",
            system_name="ServiceNow Custom",
            auth_config=auth_config,
            logo_url="https://logo.clearbit.com/servicenow.com",
            category=ToolCategory.CATEGORY_SAAS,
            tool_uses_env_vars=True,
            help="""
Use this tool to interact with ServiceNow using custom REST API calls.
"""
        )

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            self.initialize_servicenow,
            self.get_record,
            self.create_record,
            self.update_record,
            self.delete_record,
            self.query_records,
            self.get_attachment,
            self.add_attachment,
            self.delete_attachment,
            self.get_table_schema,
            self.create_incident,
            self.update_incident,
            self.resolve_incident,
            self.get_user_info,
            self.get_current_user,
            self.execute_script,
        ])

    def test_credential(self, cred, secrets: dict) -> str:
        """
        Test that the given credential secrets are valid. Return None if OK, otherwise
        return an error message.
        """
        try:
            instance_url = secrets['instance_url']
            username = secrets['username']
            password = secrets['password']
            
            # Attempt to establish a connection to ServiceNow
            session = requests.Session()
            session.auth = (username, password)
            response = session.get(f"{instance_url}/api/now/table/sys_user?sysparm_limit=1")
            response.raise_for_status()
            print("ServiceNow connection tested successfully!")
            return None  # Return None if the test is successful
        except requests.exceptions.HTTPError as http_err:
            return f"HTTP error occurred: {http_err}"
        except requests.exceptions.ConnectionError as conn_err:
            return f"Error connecting to ServiceNow: {conn_err}"
        except Exception as e:
            return f"An error occurred: {str(e)}"

    async def initialize_servicenow(self):
        """
        Initialize the ServiceNow session using the stored credentials.
        """
        self.instance_url = self.credentials['instance_url']
        username = self.credentials['username']
        password = self.credentials['password']

        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        return "ServiceNow session initialized successfully."

    async def get_record(self, table: str, sys_id: str):
        """
        Retrieve a single record from a ServiceNow table.
        
        :param table: The name of the table (e.g., 'incident', 'problem', 'change_request')
        :param sys_id: The sys_id of the record to retrieve
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.get(f"{self.instance_url}/api/now/table/{table}/{sys_id}")
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error retrieving record: {str(e)}"

    async def create_record(self, table: str, data: str):
        """
        Create a new record in a ServiceNow table.
        
        :param table: The name of the table (e.g., 'incident', 'problem', 'change_request')
        :param data: A JSON string containing the fields and values for the new record
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.post(f"{self.instance_url}/api/now/table/{table}", data=data)
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error creating record: {str(e)}"

    async def update_record(self, table: str, sys_id: str, data: str):
        """
        Update an existing record in a ServiceNow table.
        
        :param table: The name of the table (e.g., 'incident', 'problem', 'change_request')
        :param sys_id: The sys_id of the record to update
        :param data: A JSON string containing the fields and values to update
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.put(f"{self.instance_url}/api/now/table/{table}/{sys_id}", data=data)
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error updating record: {str(e)}"

    async def delete_record(self, table: str, sys_id: str):
        """
        Delete a record from a ServiceNow table.
        
        :param table: The name of the table (e.g., 'incident', 'problem', 'change_request')
        :param sys_id: The sys_id of the record to delete
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.delete(f"{self.instance_url}/api/now/table/{table}/{sys_id}")
            response.raise_for_status()
            return "Record deleted successfully" if response.status_code == 204 else "Failed to delete record"
        except requests.exceptions.RequestException as e:
            return f"Error deleting record: {str(e)}"

    async def query_records(self, table: str, query: str, limit: int = 10):
        """
        Query records from a ServiceNow table using a query string.
        
        :param table: The name of the table (e.g., 'incident', 'problem', 'change_request')
        :param query: A query string (e.g., 'active=true^priority=1')
        :param limit: The maximum number of records to return (default: 10)
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            params = {
                'sysparm_query': query,
                'sysparm_limit': limit
            }
            response = self.session.get(f"{self.instance_url}/api/now/table/{table}", params=params)
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error querying records: {str(e)}"

    async def get_attachment(self, sys_id: str):
        """
        Retrieve an attachment from ServiceNow.
        
        :param sys_id: The sys_id of the attachment
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.get(f"{self.instance_url}/api/now/attachment/{sys_id}")
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error retrieving attachment: {str(e)}"

    async def add_attachment(self, table: str, sys_id: str, file_path: str):
        """
        Add an attachment to a ServiceNow record.
        
        :param table: The name of the table (e.g., 'incident', 'problem', 'change_request')
        :param sys_id: The sys_id of the record to attach the file to
        :param file_path: The path to the file to be attached
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            with open(file_path, 'rb') as file:
                files = {'file': file}
                response = self.session.post(f"{self.instance_url}/api/now/attachment/file?table_name={table}&table_sys_id={sys_id}", files=files)
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error adding attachment: {str(e)}"

    async def delete_attachment(self, sys_id: str):
        """
        Delete an attachment from ServiceNow.
        
        :param sys_id: The sys_id of the attachment to delete
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.delete(f"{self.instance_url}/api/now/attachment/{sys_id}")
            response.raise_for_status()
            return "Attachment deleted successfully" if response.status_code == 204 else "Failed to delete attachment"
        except requests.exceptions.RequestException as e:
            return f"Error deleting attachment: {str(e)}"

    async def get_table_schema(self, table: str):
        """
        Retrieve the schema of a ServiceNow table.
        
        :param table: The name of the table (e.g., 'incident', 'problem', 'change_request')
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.get(f"{self.instance_url}/api/now/table/{table}?sysparm_limit=1")
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error retrieving table schema: {str(e)}"

    async def create_incident(self, short_description: str, description: str, caller_id: str, priority: int = 3):
        """
        Create a new incident in ServiceNow.
        
        :param short_description: A brief description of the incident
        :param description: A detailed description of the incident
        :param caller_id: The sys_id of the user reporting the incident
        :param priority: The priority of the incident (1-5, where 1 is highest)
        """
        incident_data = {
            "short_description": short_description,
            "description": description,
            "caller_id": caller_id,
            "priority": priority,
        }
        return await self.create_record("incident", json.dumps(incident_data))

    async def update_incident(self, sys_id: str, update_data: str):
        """
        Update an existing incident in ServiceNow.
        
        :param sys_id: The sys_id of the incident to update
        :param update_data: A JSON string containing the fields and values to update
        """
        return await self.update_record("incident", sys_id, update_data)

    async def resolve_incident(self, sys_id: str, resolution_notes: str):
        """
        Resolve an incident in ServiceNow.
        
        :param sys_id: The sys_id of the incident to resolve
        :param resolution_notes: Notes describing how the incident was resolved
        """
        resolve_data = {
            "state": 6,  # 6 is typically the 'Resolved' state
            "close_notes": resolution_notes,
            "resolved_at": datetime.now().isoformat(),
        }
        return await self.update_record("incident", sys_id, json.dumps(resolve_data))

    async def get_user_info(self, user_id: str):
        """
        Retrieve information about a specific user in ServiceNow.
        
        :param user_id: The sys_id of the user
        """
        return await self.get_record("sys_user", user_id)

    async def get_current_user(self):
        """
        Retrieve information about the currently logged-in user.
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.get(f"{self.instance_url}/api/now/table/sys_user?sysparm_query=user_name={self.session.auth[0]}")
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error retrieving current user info: {str(e)}"

    async def execute_script(self, script: str):
        """
        Execute a server-side script in ServiceNow.
        
        :param script: The server-side script to execute
        """
        if not self.session:
            return "Please initialize ServiceNow session first."
        
        try:
            response = self.session.post(f"{self.instance_url}/api/now/table/sys_script", json={"script": script})
            response.raise_for_status()
            return json.dumps(response.json())
        except requests.exceptions.RequestException as e:
            return f"Error executing script: {str(e)}"
