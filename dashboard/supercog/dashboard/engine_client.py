import copy
import io
import os
import requests
import re
import json
import traceback
from typing import Callable

import jwt
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.types import (PrivateKeyTypes)
import datetime
import base64

import reflex as rx
from fastapi.encoders import jsonable_encoder
from fastapi import File
from pydantic import BaseModel
import pandas as pd
import rollbar

from supercog.dashboard.models import Agent, GUEST_USER_ID
from supercog.shared.logging import logger

from supercog.shared.services import get_service_host, config
from supercog.shared.models import (
    CredentialBase, 
    RunUpdate, 
    RunOutput, 
    RunLogBase, 
    Datum, 
    DocIndexBase,
    DocSourceConfigCreate,
)

import inspect
from functools import wraps
from requests.exceptions import JSONDecodeError
from typing import Union, Any, List, Optional, Tuple, Dict

DEBUG = True
from dataclasses import dataclass


@dataclass
class ReflectionResult:
    facts:       List[str]
    analysis:    str
    token_usage: Dict[str, int]
    
class TestResult(BaseModel):
    success: bool
    message: Optional[str] = None

def safe_return(default_return_type=None):
    def decorator(func):
        # Determine the return type from annotations or use a provided default
        return_type = func.__annotations__.get('return', default_return_type)
        is_list = str(return_type).startswith("list")
        is_dict = str(return_type).startswith("dict")

        def empty_return_value():
            if is_list:
                return []
            elif is_dict:
                return {}
            elif inspect.isclass(return_type):
                return return_type()
            elif return_type is None:
                return None
            else:
                # Return a basic empty/zero value for some built-in types
                return return_type()

        def set_status_msg(args, msg):
            if args and args[0]:
                args[0].status_message = msg
            

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                set_status_msg(args, "")
                return func(*args, **kwargs)
            except requests.exceptions.ConnectionError:
                set_status_msg(args, "Cannot connect to Agents service")
                return empty_return_value()
            except requests.exceptions.HTTPError as e:
                try:
                    d = e.response.json()['detail']
                    set_status_msg(args, f"Agentsvc error: {d}")
                except:
                    set_status_msg(args, f"Agentsvc error: {e}")
                return empty_return_value()
            except Exception as e:
                # Log the exception or handle it as needed
                print(f"An error occurred: {e}")
                msg = str(e)
                if hasattr(e, 'response'):
                    msg = e.response
                traceback.print_exc()
                set_status_msg(args, f"Internal error: {msg}")
                # Return a default instance of the return type if it's a class
                return empty_return_value()

        return wrapper
    return decorator

class EngineClient:
    signing_key: PrivateKeyTypes = None
    user_token: str = ""
    user_name: str = ""
    user_timezone: str = ""
    user_id: str = ""
    user_email: str = ""
    tenant_id: str = ""
    models: list = []

    def __init__(self):
        self.base = get_service_host("engine")
        print("EngineClient init, ENGINE_URL: ", self.base)
        self.models = []
        self.status_message = ""
        self.load_private_key()

    def __deepcopy__(self, memo):
        # Create a new instance of the class
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result

        for k, v in self.__dict__.items():
            if k != 'signing_key':
                setattr(result, k, copy.deepcopy(v, memo))
        # Hopefully ok to share our signing key since it doesn't change
        result.signing_key = self.signing_key
        return result

    def __getstate__(self):
        # Return a dict of serializable fields
        state = self.__dict__.copy()
        # Remove the non-serializable field
        if 'signing_key' in state:
            del state['signing_key']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def load_private_key(self):
        private_key_pem = config.get_global('DASH_PRIVATE_KEY', required=False)
        if not private_key_pem:
            logger.warn("DASH_PRIVATE_KEY environment variable not set")
            return
        
        private_key_bytes = base64.b64decode(private_key_pem)
        private_key = serialization.load_pem_private_key(
            private_key_bytes,
            password=None,
            backend=default_backend()
        )
        self.signing_key = private_key

    def user_login(self, tenant_id: str, user_id: str, name: str, user_email: str|None=None, timezone: str = None, force: bool=False):
        if self.user_id == user_id and self.user_token and not force:
            return
        self.user_email = user_email or ""
        if self.signing_key is None:
            self.load_private_key()
            if self.signing_key is None:
                print("Self signing key is null")
                return

        self.user_id = user_id
        self.tenant_id = tenant_id
        self.user_name = name
        self.user_timezone = timezone
        print(f"Calculating JWT from {tenant_id} and {user_id} and key: ", str(self.signing_key)[0:10])
        payload = {
            'sub': user_id,
            'tenant_id': tenant_id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24),
            'email': user_email,
            'name': name,
            'timezone': timezone
        }
        token = jwt.encode(payload, self.signing_key, algorithm='ES256')
        self.user_token = token
        if config.get_global("DEBUG", required=False):
            print(f"{id(self)} User token: ", self.user_token)

    def relogin(self):
        self.user_login(
            self.tenant_id, 
            self.user_id, 
            self.user_name, 
            user_email=self.user_email, 
            timezone=self.user_timezone, 
            force=True
        )

    def validate_user_id(self, user_id: str):
        # This verifies that our "logged in" user matches the user_id we are getting
        # in the service request.
        if self.user_id != user_id:
            traceback.print_stack()
            raise ValueError(f"{id(self)} EngineClient User ID mismatch, {self.user_id} vs. {user_id}")
        
    def is_logged_in(self):
        if self.user_token:
            return True
        else:
            return False
    
    def logout(self):
        self.user_token = ""

    def debug(self, msg: str):
        if DEBUG:
            print("[agentsvc] --> ", msg)

    def _simple_request(self, method: str, path: str, **kwargs) -> requests.Response:
        headers = {}
        if self.user_token:
            headers = {
                "Authorization": f"Bearer {self.user_token}"
            }

        r = getattr(requests, method)(self.base + path, headers=headers, **kwargs)
        if r.status_code == 401:
            print("401 from Agentsvc, refreshing JWT")
            if self.user_id and self.tenant_id:
                print("calling user login with ", self.tenant_id, self.user_id)
                self.relogin()
                headers = {
                    "Authorization": f"Bearer {self.user_token}"
                }
                return getattr(requests, method)(self.base + path, headers=headers, **kwargs)
            else:
                rollbar.report_message(f"Dasbhoard cant refresh JWT", extra_data={"user_id":self.user_id, "tenant_id": self.tenant_id})
        return r

    def _get(self, path: str, params={}) -> requests.Response:
        return self._simple_request("get", path, params=params)

    def _put(self, path:str, params={}) -> requests.Response:
        return self._simple_request("put", path, params=params)

    def _delete(self, path:str, **kwargs) -> requests.Response:
        return self._simple_request("delete", path, **kwargs)

    def _post(self, path:str, **kwargs) -> requests.Response:
        headers = {}
        if self.user_token:
            headers = {
                "Authorization": f"Bearer {self.user_token}"
            }
        r = requests.post(self.base + path, headers=headers, **kwargs)
        if r.status_code == 401:
            print("401 from Agentsvc POST, refreshing JWT")
            if self.user_id and self.tenant_id:
                print("calling user login with ", self.tenant_id, self.user_id)
                self.relogin()
                headers = {
                    "Authorization": f"Bearer {self.user_token}"
                }
                return requests.post(self.base + path, headers=headers, **kwargs)
            else:
                rollbar.report_message(f"Dasbhoard cant refresh JWT", extra_data={"user_id":self.user_id, "tenant_id": self.tenant_id})
        return r

    @safe_return()
    def avail_models(self) -> list:
        if not self.models:
            self.debug("/models")
            r = self._get("/models")
            self.models = r.json()
        return self.models

    @safe_return()
    def tool_factories(self, tenant_id) -> list[dict]:
        self.debug("/tool_factories")
        try:
            r = self._get(f"/tenant/{tenant_id}/tool_factories")
            r.raise_for_status()  # Raises an HTTPError for bad responses (4XX, 5XX)

            # Check if the response body is not empty
            if not r.text.strip():
                raise ValueError("Response body is empty")

            # Attempt to decode JSON
            self._tool_factories = r.json()
            return self._tool_factories
        except JSONDecodeError as e:
            print(f"Failed to decode JSON: {e}")
            print(f"Response content: {r.text}")
        except Exception as e:
            print(f"An error occurred: {e}")
        

    def save_agent(self, agent: Agent, run_id: str|None=None) -> dict:
        # post the Agent to the Engine
        print("POST agent: ", agent.name)
        params = {}
        if run_id:
            params['run_id'] = run_id
        r = self._post("/agents", params=params, json=agent.network_dump())
        r.raise_for_status()
        return r.json()

    def create_run(self, tenant_id, user_id, agent: Agent,
                   logs_channel: str, conversation_id: str | None = None) -> dict:
        self.validate_user_id(user_id)
        req_json = {
            "tenant_id": tenant_id + "",
            "user_id": user_id + "",
            "agent_id": agent.id,
            "input_mode": "truncate",
            "logs_channel": logs_channel,
            "conversation_id": conversation_id,
            "scope": agent.scope,
        }
        logger.info("POSTing run: ", req_json, " and logs_channel: ", logs_channel)
        r = self._post("/runs", json=req_json)
        r.raise_for_status()
        return r.json()

    def update_run(self, user_id, run_id: str, run_update: RunUpdate):
        self.validate_user_id(user_id)
        r = self._simple_request("patch", f"/runs/{run_id}", json=run_update.model_dump(exclude_none=True))
        r.raise_for_status()
        return r.json()
    
    def send_input(self, run_id, question, attached_file: str|None=None, run_data: Optional[dict] = None):
        params = {}
        if attached_file:
            params["attached_file"] = attached_file

        body = {"input": question or ""}
        if run_data:
            body["run_data"] = run_data
            
        r = self._post("/runs/" + run_id + "/input",
                    json=body, params=params
        )
        if r.status_code != 200:
            self.status_message = "Error calling engine service: " + r.text
            print("Error calling engine service: ",r, r.status_code)
            return

    def cancel_run(self, run_id):
        r = self._put("/runs/" + run_id + "/cancel")
        if r.status_code != 200:
            self.status_message = "Error calling engine service: " + r.text
            print("Error calling engine service: ", r.text)
            return
        
    def get_todays_runs(self, tenant_id) -> list[RunOutput]:
        r = self._get(f"/tenant/{tenant_id}/runs")
        r.raise_for_status()
        return [
            RunOutput.model_validate(record)
            for record in r.json()
        ]
    
    @safe_return()
    def get_runs(self, agent: Agent, user_id: str) -> list[RunOutput]:
        self.validate_user_id(user_id)
        self.debug("tenant/runs")
        r = self._get(f"/tenant/{agent.tenant_id}/agents/{agent.id}/runs",
                         params={"user_id": user_id})
        if r.status_code == 404:
            # Agent may not be posted to Agentsvc yet
            return []
        r.raise_for_status()
        return [RunOutput.model_validate(rec) for rec in r.json()]
    
    @safe_return()
    def get_run(self, run_id: str) -> dict:
        r = self._get(f"/runs/{run_id}")
        r.raise_for_status()
        # FIXME: Update to RunOutput
        return r.json()
    
    @safe_return()
    def get_run_logs(self, run_id: str, user_id: str) -> list[RunLogBase]:
        self.validate_user_id(user_id)
        self.debug(f"runs/{run_id}/run_logs")
        r = self._get(f"/runs/{run_id}/run_logs", params={"user_id": user_id})
        r.raise_for_status()
        try:
            return [RunLogBase.model_validate(rec) for rec in r.json()]
        except Exception as e:
            print("error parsing run logs: ", e)
            print(r.text)
            return []
    
    @safe_return()
    async def delete_run_logs(self, run_id: str, user_id: str) -> None:
        self.validate_user_id(user_id)
        self.debug(f"Deleting run logs for run {run_id}")
        r = self._delete(f"/runs/{run_id}/run_logs", params={"user_id": user_id})
        if r.status_code != 200:
            raise RuntimeError(f"Error deleting run logs: {r.json()}")
        
    @safe_return()
    async def delete_run(self, run_id: str) -> None:
        r = self._delete(f"/runs/{run_id}")
        if r.status_code != 200:
            raise RuntimeError("Error deleting run: ", r.json())

    @safe_return()
    def reflect(self, run_id: str, user_id: str) -> ReflectionResult:
        """
        Get reflection facts and token usage for a specific run.
        
        Args:
            run_id: The ID of the run to reflect on
            user_id: The ID of the user
            
        Returns:
            ReflectionResult containing facts list and token usage dictionary
        """
        self.debug("reflect")
        
        r = self._get(f"/runs/{run_id}/reflect", params={"user_id": user_id})
        r.raise_for_status()
        
        response_data = r.json()
        return ReflectionResult(
            facts=       response_data["facts"],
            analysis =   response_data["analysis"],
            token_usage= response_data["token_usage"]
        )
    
    @safe_return()
    def get_run_datums(self,
                       tenant_id: str,
                       agent_id:  str,
                       user_id:   str,
                       run_id:    str,
                       directory: Optional[str] = None) -> list[Datum]:
        self.debug(f"/tenant/agent/runs/datums")
        params = {"user_id": user_id}
        if directory:
            params['directory'] = directory  # Assuming the API can handle a 'directory' parameter
        r = self._get(f"/tenant/{tenant_id}/agents/{agent_id}/run/{run_id}/datums", params=params)
        r.raise_for_status()
        return [Datum.model_validate(rec) for rec in r.json()]



    def get_run_datum(self,
                      tenant_id: str,
                      agent_id,
                      user_id: str,
                      run_id: str,
                      category: str,
                      name: str) -> Tuple[str, Union[str, pd.DataFrame, dict, Any]]:
        self.debug(f"/tenant/agent/run/datum")
        # FIXME: We should use response streaming to avoid too much buffering
        try:
            r = self._get(
                f"/tenant/{tenant_id}/agents/{agent_id}/run/{run_id}/getdatum", 
                params={"user_id": user_id, "category": category, "name": name}
            )
            r.raise_for_status()
            response_json = r.json()
            content_type = response_json.get('type', '')
            content = response_json.get('content', {})
            if not content:
                return "error", f"No content returned for {name}"
            file_type = content.get('type', '')
            if file_type == "csv":
                content['raw_data'] = pd.read_csv(io.StringIO(content.get('raw_data', '')))
            elif file_type in ["json", "email"]:
                try:
                    content['raw_data'] = json.loads(content.get('raw_data', '{}'))
                except json.JSONDecodeError:
                    # Keep the original string if it's not valid JSON
                    pass
            return file_type, content
        except requests.exceptions.HTTPError as http_err:
            if http_err.response.status_code == 404:
                return "error", f"File '{name}' not found in SupercogFS"
            else:
                # Re-raise other HTTP errors
                raise
        except Exception as e:
            return "error", f"Error retrieving file '{name}': {str(e)}"

    def delete_run_datum(self, tenant_id: str, agent_id, user_id: str, run_id: str, category: str, name: str):
        self.debug(f"DEL /tenant/agent/run/datum/{name}")

        r = self._delete(
            f"/tenant/{tenant_id}/agents/{agent_id}/run/{run_id}/getdatum", 
            params={"user_id": user_id, "category": category, "name": name}
        )
        r.raise_for_status()
        return r.json()

    def _remove_redacted_secrets(self, secrets: dict):
        for key in list(secrets.keys()):
            if bool(re.match(r'^\*+$', secrets[key])):
                del secrets[key]

    def set_credential(
            self, 
            tenant_id, 
            user_id, 
            credential_id: str | None,
            tool_factory_id: str, 
            name: str,
            is_shared: bool,
            secrets: dict) -> CredentialBase:

        # Make a copy to not deal with reflex funniness
        secrets_dict = dict(secrets)
            
        # Remove secrets that are redacted
        self._remove_redacted_secrets(secrets_dict)
                
        credential = CredentialBase(
            name=name,
            tenant_id=tenant_id,
            user_id=user_id,
            scope="shared" if is_shared else "private",
            tool_factory_id=tool_factory_id,
            secrets_json=json.dumps(secrets_dict)
        )
        if credential_id:
            response = self._simple_request("patch", f"/tenant/{tenant_id}/credentials/{credential_id}",
                            json=credential.model_dump(exclude={'id'}))
        else:
            response = self._post(f"/tenant/{tenant_id}/credentials",
                            json=credential.model_dump(exclude={'id'}))
        assert response.status_code == 200

        credential = CredentialBase.model_validate(response.json())
        return credential

    @safe_return()
    def get_credential(self, tenant_id, user_id, key) -> dict:
        r = self._get(
            f"/tenant/{tenant_id}/credentials/{key}", 
            params={"user_id": user_id}
        )
        if r.status_code != 200:
            raise RuntimeError("Error getting credentials: ", r.json())
        return r.json()

    # Tests if a credential still works, and returns a result dict with 'success' bool
    # and 'message' string. This thing is subtle. When creating a new Cred, then we use
    # the secrets from the UI form. Easy enough.
    # But if the Cred has already been saved, then we want to use the Saved creds. HOWEVER,
    # if the user has provided any new values, then we want to merge those with the saved
    # ones and test those. So we send any edited Form secrets and let the backend merge those
    # with the saved values to test. We know Form vals are "edited" if there are not just stars.
    def test_credential(
            self, 
            tenant_id, 
            user_id, 
            tool_factory_id: str="",
            credential_id: str|None=None, 
            secrets: dict = {}) -> TestResult:
        exclude = {}

        if credential_id:
            # Cred already saved, so strip secrets that look redacted
            self._remove_redacted_secrets(secrets)
            credential = CredentialBase(
                id=credential_id,
                name="",
                tenant_id=tenant_id,
                user_id=user_id,
                tool_factory_id=tool_factory_id,
                secrets_json=json.dumps(secrets),
            )
        else:
            credential = CredentialBase(
                name="",
                tenant_id=tenant_id,
                user_id=user_id,
                tool_factory_id=tool_factory_id,
                secrets_json=json.dumps(secrets)
            )
            exclude = {'id'}
        r = self._post(
            f"/tenant/{tenant_id}/credentials/test", 
            json=credential.model_dump(exclude=exclude),
        )
        r.raise_for_status()
        print("Result after testing credentials: ", r.json())
        return TestResult(**r.json())

    @safe_return()
    def list_credentials(self, tenant_id, user_id) -> list[dict]:
        if user_id == GUEST_USER_ID:
            return []
        self.debug("/credentials")
        r = self._get(f"/tenant/{tenant_id}/credentials", params={"user_id": user_id})
        if r.status_code != 200:
            raise RuntimeError("Error getting credentials: ", r.json())
        return r.json()

    def delete_credential(self, tenant_id, user_id, credential_id):
        r = self._delete(
            f"/tenant/{tenant_id}/credentials/{credential_id}", 
            params={"user_id": user_id}
        )
        if r.status_code != 200:
            raise RuntimeError("Error deleting credentials: ", r.json())
        
    def user_secrets(self, tenant_id: str, user_id: str) -> dict[str,str]:
        self.debug("/user_secrets")
        r = self._get(f"/tenant/{tenant_id}/{user_id}/secrets")
        r.raise_for_status()
        # return secrets dict as list of key, value pairs
        return r.json()['secrets']
    
    def save_secrets(self, tenant_id: str, user_id: str, secrets: dict[str, str]):
        self.debug("POST /user_secrets")
        r = self._post(
            f"/tenant/{tenant_id}/{user_id}/secrets", 
            json={"secrets" : dict(secrets)}
        )
        r.raise_for_status()

    def delete_secret(self, tenant_id: str, user_id: str, key: str):
        self.debug("DEL /user_secrets")
        r = self._delete(f"/tenant/{tenant_id}/{user_id}/secrets", params={"key": key})
        r.raise_for_status()

    def create_doc_index(self, tenant_id, user_id, index_name: str, scope: str = "private") -> dict:
        record = DocIndexBase(
            name=index_name,
            tenant_id=tenant_id,
            user_id=user_id,
            scope=scope,
        )
        r = self._post(f"/tenant/{tenant_id}/doc_indexes", json=record.model_dump(exclude={'id'}))
        r.raise_for_status()
        return r.json()

    def delete_doc_index(self, tenant_id, user_id, index_id: str) -> dict:
        r = self._delete(f"/tenant/{tenant_id}/doc_indexes/{index_id}", params={"user_id": user_id})
        r.raise_for_status()
        return r.json()

    @safe_return()
    def list_doc_indexes(self, tenant_id, user_id, transform: Callable|None=None) -> list:
        self.debug("/doc_indexes")
        r = self._get(f"/tenant/{tenant_id}/doc_indexes", params={"user_id": user_id})
        if r.status_code != 200:
            raise RuntimeError("Error getting docsources: ", r.json())
        try:
            if transform:
                return [transform(rec) for rec in r.json()]
            else:
                return r.json()
        except:
            return []

    def update_index(self, tenant_id, user_id, index_id: str, update: dict) -> dict:
        r = self._simple_request("patch", f"/tenant/{tenant_id}/doc_indexes/{index_id}", json=update)
        r.raise_for_status()
        return r.json()

    def attach_docsource_to_index(
            self, 
            tenant_id, 
            user_id, 
            index_id, 
            doc_source_factory_id, 
            doc_source_name,
            folder_ids, 
            file_patterns,
            provider_data=None
        ) -> dict:

        source = DocSourceConfigCreate(
            name=doc_source_name,
            doc_index_id=index_id,
            doc_source_factory_id=doc_source_factory_id,
            folder_ids=folder_ids,
            file_patterns=file_patterns,
            provider_data=provider_data  # This will contain the URL
        )
        # Convert to dict and ensure provider_data is included
        data = source.dict()
        if provider_data:
            data["provider_data"] = provider_data  # Ensure provider_data is explicitly set
            
        r = self._post(
            f"/tenant/{tenant_id}/doc_indexes/{index_id}/sources",
            json=data,
        )
        print("Result: ", r.text)
        r.raise_for_status()
        return r.json()

    def get_docsources(self, tenant_id, user_id, index_id) -> list[dict]:
        r = self._get(f"/tenant/{tenant_id}/doc_indexes/{index_id}/sources", params={"user_id": user_id})
        print(r.text)
        r.raise_for_status()
        return r.json()

    def get_docsource_authorize_url(self, tenant_id, index_id, source_id) -> str:
        r = self._get(f"/tenant/{tenant_id}/doc_indexes/{index_id}/sources/{source_id}/authorize")
        r.raise_for_status()
        return r.json()['authorize_url']
    
    def authorize_callback(self, tenant_id, index_id, source_id, params: dict):
        r = self._post(
            f"/tenant/{tenant_id}/doc_indexes/{index_id}/sources/{source_id}/authorize_callback",
            json=params
        )
        r.raise_for_status()
        return r.json()

    def delete_docsource(self, tenant_id, user_id, index_id, config_id):
        r = self._delete(
            f"/tenant/{tenant_id}/doc_indexes/{index_id}/sources/{config_id}",
            params={"user_id": user_id}
        )
        r.raise_for_status()
        return r.json()

    def get_doc_index(self, tenant_id, index_id) -> DocIndexBase:
        r = self._get(f"/tenant/{tenant_id}/doc_indexes/{index_id}")
        r.raise_for_status()
        return DocIndexBase.model_validate(r.json())

    async def upload_index_file(
            self, 
            tenant_id: str, 
            user_id: str, 
            index_id: str,
            file: rx.UploadFile
        ):
        content = await file.read()
        r = self._post(
            f"/tenant/{tenant_id}/doc_indexes/{index_id}/files",
            params={"user_id": user_id},
            files={
                "file": (file.filename, content, file.content_type)
            }
        )
        r.raise_for_status()

    def delete_index_file(self, tenant_id, user_id, index_id: str, doc_id: str):
        r = self._delete(f"/tenant/{tenant_id}/doc_indexes/{index_id}/files/{doc_id}")
        r.raise_for_status()

    def get_index_files(self, tenant_id, user_id, index_id,target_page) -> list[dict]:
        r = self._get(f"/tenant/{tenant_id}/doc_indexes/{index_id}/page/{target_page}/files", params={"user_id": user_id})
        r.raise_for_status()
        recs = r.json()
        for rec in recs:
            rec["show_id"] = rec["id"].split("-")[0]
        return recs


    def index_search(self, tenant_id, user_id, index_id, query:str) -> list[dict]:
        r = self._get(f"/tenant/{tenant_id}/doc_indexes/{index_id}/search", params={"user_id": user_id, "query": query})
        r.raise_for_status()
        return r.json()

    def stuff_google_credential_for_user(
            self,
            tenant_id,
            user_id,
            access_token: str,
            refresh_token: str,
            id_token: str,
            expires_at: float,
        ):
        existing_id = None
        for cred in self.list_credentials(tenant_id, user_id):
            if cred['tool_factory_id'] == 'gmail_connector' and cred['name'] == 'login credential':
                existing_id = cred['id']
                break

        self.set_credential(
            tenant_id,
            user_id,
            existing_id,
            'gmail_connector',
            'login credential',
            False,
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "id_token": id_token,
                "expires_at": str(expires_at)
            }
        )
    
    @safe_return()
    def list_files(self, state_obj, tenant_id, folder, drive='default') -> list[dict]:
        self.state_obj = state_obj
        r = self._get(f"/tenant/{tenant_id}/{drive}/files/{folder}")
        r.raise_for_status()
        return r.json()
    
    @safe_return()
    def list_folders(self, tenant_id, folder, drive='default') -> list[str]:
        r = self._get(f"/tenant/{tenant_id}/{drive}/folders")
        r.raise_for_status()
        return r.json()
    
    async def upload_file(
            self, 
            tenant_id: str, 
            user_id: str, 
            folder: str,
            file: rx.UploadFile,
            drive: str = 'default',
            index_file: bool = False,
            run_id: str|None=None
        ):
        content = await file.read()
        r = self._post(
            f"/tenant/{tenant_id}/{drive}/files",
            params={"folder": self.user_id + ":" + folder, "index": index_file, "run_id": run_id},
            files={
                "file": (file.filename, content, file.content_type)
            }
        )
        r.raise_for_status()

    async def upload_slack_file(self, folder: str, file_name: str, content: bytes,
                    content_type: str,
                    drive: str = 'default',
                    index_file: bool = False,
                    run_id: str|None=None):
        r = self._post(
            f"/tenant/{self.tenant_id}/{drive}/files",
            params={"folder": self.user_id + ":" + folder, "index": index_file, "run_id": run_id},
            files={
                "file": (file_name, content, content_type)
            }
        )
        r.raise_for_status()

    def delete_file(self, tenant_id, user_id: str, filename: str, drive='default'):
        folder = os.path.dirname(filename)
        filename = os.path.basename(filename)

        folder = user_id + ":" + folder
        r = self._delete(f"/tenant/{tenant_id}/{drive}/files/{folder}",
                            params={"filename": filename})
        r.raise_for_status()
        print("Delete returned: ", r.text)

    def delete_files(self, tenant_id, user_id: str, filenames: list[str], drive='default'):
        if not filenames:
            return "No files to delete"

        # Construct the folder from the first filename, similar to delete_file
        # FIXME: this is a big assumption.
        folder = os.path.dirname(filenames[0])
        folder = user_id + ":" + folder

        # Extract just the filenames without the path
        basenames = [os.path.basename(filename) for filename in filenames]

        r = self._delete(
            f"/tenant/{tenant_id}/{drive}/files/{folder}/batch",
            json=basenames
        )
        r.raise_for_status()

        result = r.json()

        # Error handling and result processing
        if "error" in result:
            print(f"Error deleting files: {result['error']}")
        else:
            deleted_count = len(result.get('deleted', []))
            error_count = len(result.get('errors', []))
            print(f"Deleted {deleted_count} files. Errors: {error_count}.")

            if error_count > 0:
                for error in result.get('errors', []):
                    print(f"Error deleting {error['Key']}: {error['Code']} - {error['Message']}")

        return result

    def get_file_info(self, tenant_id, user_id: str, filename: str, drive='default') -> dict:
        folder = os.path.dirname(filename)
        filename = os.path.basename(filename)
        folder = user_id + ":" + folder

        r = self._get(f"/tenant/{tenant_id}/{drive}/file/{folder}",
                        params={"filename": filename})
        r.raise_for_status()
        return r.json()
    
    @safe_return()
    def get_admin_info(self, tenant_id) -> tuple[list[dict],list[RunOutput],dict]:
        r = self._get(f"/admin/runs")
        r.raise_for_status()
        results = r.json()
        agents = results['agents']
        runs = results['runs']
        return agents, runs, results['info']

    @safe_return()
    def get_daily_usage(self, tenant_id: str, user_id: str) -> dict:
        r = self._get(f"/tenant/{tenant_id}/daily_stats", params={"user_id": user_id})
        r.raise_for_status()
        return r.json()
    
