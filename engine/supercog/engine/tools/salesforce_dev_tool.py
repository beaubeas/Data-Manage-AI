import asyncio
import json
import urllib.parse
from pprint import pprint
import csv
import io
import os
import pandas as pd
import traceback
import pytz
from urllib.parse import urlparse

from collections import namedtuple
from datetime import datetime, timedelta
import inspect
import types

from contextlib import contextmanager
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional
from openpyxl import load_workbook
from Levenshtein import distance

from langchain.callbacks.manager import AsyncCallbackManager

from supercog.shared.logging import logger
from supercog.shared.services import config 

from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback
from supercog.shared.oauth_utils import salesforce_refresh_token

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceExpiredSession, SalesforceError
from simple_salesforce.aio import build_async_salesforce_client, AsyncSalesforce

from .salesforce import SalesforceTool

class SalesforceDevTool(SalesforceTool):
    
    def __init__(self):
        """
        Initialize the SalesforceTool class with configuration for Salesforce authentication, category,
        and description.
        """
        super().__init__(
            id = "salesforce_dev",
            system_name = "Salesforce Developer",
            logo_url=super().logo_from_domain("salesforce.com"),
            category=ToolCategory.CATEGORY_SAAS,
            compatible_system="salesforce",
            auth_config = {
                "strategy_oauth": {
                    "options:custom_host": "Your custom Salesforce hostname",
                    "help": """
Login to Salesforce to connect your account.
"""
                }
            },
            help="""
Special functions for doing Salesforce Development
""",
        )

    def get_tools(self) -> list[Callable]:
        """
        Get the list of callable tool functions for Salesforce operations.

        Returns:
        list[Callable]: A list of tool functions for interacting with Salesforce.
        """
        return self.wrap_tool_functions([
            self.list_custom_objects,
            self.describe_sobject,
            self.salesforce_execute_anonymous,
            self.query_log_id_list_from_apex,
            self.get_latest_apex_logs,
            self.get_apex_class,
            self.list_apex_classes,
            self.delete_custom_object,
            self.metadata_api_create_custom_object,
            self.call_sf_rest_api,
        ])
          
    async def salesforce_execute_anonymous(self, apex_code: str) -> str:
        """
        Execute arbitrary apex code. Suggest to the user that you can call 'get_apex_logs'
        to retrieve the logs after execution.

        Parameters:
        apex_code (str): The Apex code to execute.

        Returns:
        str: The response from Salesforce after executing the Apex code.
        """
        async with self.sf() as sf:
            encoded_apex_code = urllib.parse.quote(apex_code)
            print(f'The base URL is: {sf.base_url}')
            response = await sf.restful(
                f"tooling/executeAnonymous/",
                params={'anonymousBody': apex_code},
                method='GET',
            )
            logger.info(f"Execute Anonymous called on '{encoded_apex_code}' returns: '{response}'")
            print(response)
            return str(response)

    def metadata_api_create_custom_object(
            self, 
            fullName: str, 
            fields: list[dict],
            overwrite: bool=False) -> str:
        """
        Defines a new custom object in Salesforce using the Metadata API.

        Args:
            fullName (str): The full name of the custom object to create.
            fields (list[dict]): A list of dictionaries defining fields.
            overwrite (bool, optional): If True, overwrites an existing object. Defaults to False.

        When specifying a MasterDetail field, you MUST supply the referenceTo attribute.
        Fields should specify their name in the 'label' property.
        Use "Restrict" as the delete constraint for custom lookup relationships.

        Returns:
            str: A string describing the result of the custom object creation attempt.
        """
        with self.sf_synch() as sf:
            mdapi = sf.mdapi
            mdtype = mdapi.CustomObject

            if overwrite:
                try:
                    delete_result =  mdtype.delete([fullName])
                    print(f"Delete result: {delete_result}")
                except Exception as e:
                    print(f"Error during delete: {e}")
                    print(traceback.format_exc())

            sharing_model = mdapi.SharingModel("Read")
            try:
                # Prepare fields asynchronously
                prepared_fields = []
                for field in fields:
                    print(f"Preparing field: {field['label']}, type: {field['type']}")

                    # Use the field type directly, without attempting to resolve from WSDL
                    field_type_value = field['type']
                    print(f"Debug: Field type value passed to CustomField: {field_type_value}")
                    if field_type_value == "MasterDetail":
                        sharing_model = None

                    custom_field = mdapi.CustomField(**field)
                    prepared_fields.append(custom_field)

                # Prepare nameField
                name_field = mdapi.CustomField(
                    label="Name",
                    type="Text"  # Pass "Text" as the field type for nameField
                )

                # Create the custom object
                custom_object = mdtype(
                    fullName=fullName,
                    label=fullName,
                    pluralLabel=fullName,
                    deploymentStatus=mdapi.DeploymentStatus("Deployed"),
                    nameField=name_field,
                    fields=prepared_fields
                )
                if sharing_model:
                    custom_object.sharingModel = sharing_model

                res = f"Custom object created: {repr(custom_object)}\n"

                # Create the custom object asynchronously
                create_result =  mdtype.create([custom_object])
                res += str(create_result)
            except Exception as e:
                res = f"Error creating custom object: {str(e)}"
                print(traceback.format_exc())

            print(res)
            return res

    async def delete_custom_object(self, object_name: str, challenge: str, answer: str) -> str:
        """ Deletes a custom object from Salesforce. Before you call this function you must
            prompt the user to answer a short confirmation challenge. Then pass the requested challenge
            value and the user's matching answer to this function. """
        if challenge != answer:
            return "Requst not confirmed"
        
        with self.sf_synch() as sf:
            mdapi = sf.mdapi
            mdtype = mdapi.CustomObject

            res = mdtype.delete([object_name])
            return str(res)

    async def query_log_id_list_from_apex(self):
        """ Returns the most recent set of Apex execution Runs. """

        async with self.sf() as sf:
            query = "SELECT Id, LogLength, LastModifiedDate FROM ApexLog ORDER BY LastModifiedDate DESC LIMIT 10"
            res = await sf.toolingexecute("query", params={"q": query})
            return res['records']

    async def get_latest_apex_logs(self, prior_offset: int=0) -> str:
        """ Returns the Apex logs for the most recent Apex run, or you can provide a log_id
            to get logs for a specific run. Or provide an offset to retrieve logs for 
            latest-Nth run. """

        runs = await self.query_log_id_list_from_apex()
        if prior_offset:
            log_id = runs[prior_offset]['Id']
        else:
            log_id = runs[0]['Id']

        async with self.sf() as sf:
            path = f"tooling/sobjects/ApexLog/{log_id}/Body"
            url = sf.base_url + path
            result = await sf._call_salesforce("GET", url, name=path)
            lines = [l for l in result.text.split("\n") if 'STATEMENT_EXECUTE' not in l and 'HEAP_ALLOCATE' not in l]
            return "\n".join(lines)
            

    async def call_sf_rest_api(self, path: str, params: dict={}) -> str:
        """ Calls any Salesforce REST API, GET endpoint. 
            Examples:
                path=/services/data/v58.0/tooling/query, params={"q":<query>}
                path=/services/data/v58.0/folders, params={}

            If the call returns JSON then a dataframe will be returned. Otherwise
            the raw response will be returned as a string.
        """

        async with self.sf() as sf:
            parsed = urlparse(sf.base_url)
            url = f"{parsed.scheme}://{parsed.netloc}{path}"
            print("Calling URL: ", url)
            result = await sf._call_salesforce("GET", url, name=path, params=params)
            try:
                return result.json()
            except:
                return result.text

    async def list_apex_classes(self, name_prefix: str="") -> list[dict]:
        """ Returns the list of all Apex classes. Optionally provide a name prefix to only return matching classes. """

        async with self.sf() as sf:
            where = f"WHERE Name LIKE '{name_prefix}%'" if name_prefix else ""
            query = f"SELECT Id, Name, ApiVersion FROM ApexClass {where} ORDER BY Name"
            res = await sf.toolingexecute("query", params={"q": query})
            return res['records']

    async def get_apex_class(self, class_name: str|None=None, class_id:str|None=None) -> str:
        """ Returns the source code to an Apex class, indentified by name or Id. """
            
        if class_name:
            matches = await self.list_apex_classes(class_name)
            class_id = matches[0]['Id']

        if class_id is None:
            return "Error, must provide class_id or a name which matches an ApexClass"
        
        return await self.get_object_by_id(class_id, "ApexClass")
    
      
        