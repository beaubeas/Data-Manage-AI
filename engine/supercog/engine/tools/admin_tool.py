from supercog.engine.tool_factory import ToolFactory, ToolCategory
from contextlib import contextmanager
import json
import requests
from dateutil.relativedelta import relativedelta
from typing import Any, Callable, Optional
import time
from fastapi import FastAPI
#from supercog.dashboard.state import State
from supercog.shared.services import get_service_host
from supercog.shared.models import RunOutput


import importlib
import inspect
import functools
from datetime import datetime
import pytz
import platform
import socket
import os
import sys

class AdminTool(ToolFactory):
    openai_org_id: str=""
    openai_api_key: str=""
    tenant_id: str=""
    def __init__(self):
        
        super().__init__(
            id="admin_connector",
            system_name="Admin",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/8/80/Computer_user_icon.svg",
            auth_config={
#                "strategy_token": {
#                    "openai_api_key": "API KEY - find this at https://platform.openai.com/api-keys",
#                    "openai_org_id":  "API Org Id - find this in: https://platform.openai.com/account/organization",
#                    "help": """
#Create this in the app under tools-.options->API key and set the value here."""
#                }
            },
            category=ToolCategory.CATEGORY_BUILTINS,
            help="""
Use this tool to manage agent schedules.
"""
        )


    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            #self.get_openapi_usage_stats,
            self.get_running_job_stats,
            self.get_active_triggers,
            self.cancel_job,
            self.cancel_trigger,
            #self.describe_class,
            self.wakeup,
            self.get_current_jobs,
        ])

    @staticmethod
    def get_system_info() -> dict:
        # Time and Date
        timezone = pytz.timezone('UTC')
        current_datetime = datetime.datetime.now(timezone)
        datetime_info = current_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')

        return {
            "Current Date and Time": datetime_info,
            "Operating System": platform.platform(),
            "Python Version": platform.python_version(),
            "Hostname": socket.gethostname(),
            "IP Address": socket.gethostbyname(socket.gethostname()),
            "User": os.getlogin(),
            "Current Working Directory": os.getcwd(),
            "System Load": os.getloadavg(),
            "Python Executable": sys.executable
        }

    def wakeup(self) -> dict:
        """Return all the context the Agent needs to know where and when it exists"""
        return self.get_system_info()
    
    def prepare_creds(self, cred, secrets: dict) -> dict:
        #self.openai_org_id  = secrets['openai_org_id'] # 
        #self.openai_api_key = secrets['openai_api_key']# 
        #print(f"--------->SMS Secrets: ",json.dumps(secrets))
        return secrets
        
    def get_running_job_stats(self) -> dict:
        """
        Retrieves and returns statistics about running jobs.
        :return: A dictionary containing statistics about running jobs.
        """
        host = get_service_host("triggersvc")
        url = f"{host}/tenant/{self.run_context.tenant_id}/get_jobs"  # Correct URL formatting
        print(f'------>URL: {url}')
        try:
            response = requests.get(url)
            return response.json()  # Parses JSON response body into a dict
        except Exception as e:
            return {"error": str(e), "message": f"Failed to get running jobs  due to {response.json()}"}
        
    def get_current_jobs(self) ->  list[RunOutput]:
        """ return the list of currently running Agent jobs """
        return []
        #return State.get_current_runs()
    
    def get_active_triggers(self) -> dict:
        """
        Retrieves and returns statistics about triggers.
        :param creds_pk: A dictionary containing credentials.
        :return: A dictionary containing statistics about running jobs.
        """
        host = get_service_host("triggersvc")
        url = f"{host}/tenant/{self.run_context.tenant_id}/triggers"  # Correct URL formatting
        print(f'------>URL: {url}')
        try:
            response = requests.get(url)
            return response.json()  # Parses JSON response body into a dict
        except Exception as e:
            return {"error": str(e), "message": f"Failed to get active triggers due to {response.json()}"}
    
        
    def cancel_job(self, job_id: str) -> dict:
        """Cancel a job running on the apscheduler."""
        host = get_service_host("triggersvc")
        url = f"{host}/tenant/{self.run_context.tenant_id}/cancel_job?job_id={job_id}"  # Correct URL formatting
        print(f'------>URL: {url}')

        try:
            response = requests.get(url)
            response.raise_for_status()  # Check for HTTP errors
            return {"message": f"Job {job_id} cancellation attempted successfully.", "status": response.status_code}
        except requests.RequestException as e:
            print(f"------>Error while attempting to cancel job: {e}")
            return {"error": str(e), "message": f"Failed to cancel job due to {response.json()}"}

    def cancel_trigger(self, agent_id: str) -> dict:
        """
        cancels a running trigger.
        :param creds_pk: A dictionary containing credentials.
        :param agent_id: the agent_id of the job we want to cancel.
        """
        host = get_service_host("triggersvc")
        url = f"{host}/tenant/{self.run_context.tenant_id}/cancel_trigger?agent_id={agent_id}"  # Correct URL formatting
        print(f'------>URL: {url}')
        response = requests.get(url)
        try:
            response = requests.get(url)
            print(f"------>Response from cancel_trigger is: {response} and {response.json()}")
            response.raise_for_status()  # Check for HTTP errors
            return {"message": f"Trigger {agent_id} cancellation  successful.", "status": response.status_code}
        except requests.RequestException as e:
            print(f"------>Error while attempting to cancel trigger: {e}")
            return {"error": str(e), "message": f"Failed to cancel trigger due to {response.json()}"}
    
    def get_logged_in_users(self) -> str:
        """ return a list of users logged into LLMonster """
        return ""
        
    def get_openapi_usage_stats(self,
                                wait_time: int           = 60,
                                start_day: datetime      = None,
                                end_day:   datetime      = None) -> str:
        """
        Get usage statistics from OpenAI API calls. 
        wait_time (int): Optional; Default is 60 seconds. Time to wait for a response.
        Returns:
        str: A string representation of the usage statistics.
        """

        def get_openai_api_pricing(model="gpt-3.5-turbo-16k"):
            """Calculate the cost for prompt and completion tokens based on the model."""

            print(f'looking for pricing for model {model}')
            pricing = {
                'gpt-3.5-turbo-4k': {
                    'prompt':     0.0015,
                    'completion': 0.002,
                },
                'gpt-3.5-turbo-0125': {
                    'prompt':     0.0005,
                    'completion': 0.0015,
                },
                'gpt-3.5-turbo-1106': {
                    'prompt':     0.0015,
                    'completion': 0.002,
                },
                'gpt-3.5-turbo-16k': {
                    'prompt':     0.003,
                    'completion': 0.004,
                },
                'gpt-4-8k': {
                    'prompt':     0.003,
                    'completion': 0.006,
                },
                'gpt-4-32k': {
                    'prompt':     0.006,
                    'completion': 0.12,
                },
                'gpt-4-1106-preview': {
                    'prompt':     0.01,
                    'completion': 0.03,
                },
                'gpt-4-turbo-2024-04-09': {
                    'prompt':     0.01,
                    'completion': 0.03,
                },
                'dall-e-3': {
                    'image_small': 0.0040,
                    'image_large': 0.0080,
                },
                'text-embedding-ada-002-v2': {
                    'prompt':     0.00001,
                    'completion': 0.00001,
                },
            }
            if(model == 'dall-e-3'):
                model_pricing = pricing.get(model, {'image_small': -1, 'image_large': -1})
                return model_pricing['image_small'], model_pricing['image_large']
            else:
                model_pricing = pricing.get(model, {'prompt': -1, 'completion': -1})
                return model_pricing['prompt'], model_pricing['completion']

        def add_daily_usage(model_usage, model_name, stat_name, stat, date_str):
            if date_str not in model_usage[model_name][stat_name]:
                model_usage[model_name][stat_name][date_str] = 0
            model_usage[model_name][stat_name][date_str] += stat
    
        
       
        date_format = "%Y-%m-%d"
        first_day_of_month    = datetime.today().replace(day=1)
        if start_day == None:
            start_day = first_day_of_month
       
        current_day           = datetime.today()
        if end_day == None:
            end_day = current_day
        
        prompt_token_cost     = 0.01
        completion_token_cost = 0.03
        headers = {
            "method": "GET",
            "authority": "api.openai.com",
            "scheme": "https",
            "path": f"/v1/organizations/{self.openai_org_id}/users",
            "authorization": f"Bearer {self.openai_api_key}",
        }
        

        users_response = requests.get(f"https://api.openai.com/v1/organizations/{openai_org_id}/users", headers=headers)
        users = users_response.json()["members"]["data"]
        user_results = []  # List to hold results for all users
        for user in users:
            print('User info: \n',json.dumps(user, indent=4))
            id_of_user             = user["user"]["id"]
            name                  = user["user"]["name"] 
            email                  = user["user"]["email"] 
            total_context_tokens   = 0   # same as prompt tokens
            total_generated_tokens = 0   # same as completion tokens
            daily_costs            = {}  # Dictionary to store daily costs
            api_call_counts        = {}  # Dictionary to store API call counts per day
            model_usage            = {}  # Dictionary to store usage by model

            current_date           = start_day
            request_counter        = 0
            requests_per_minute    = 4 # current openai limit
            
            start_time = time.time()
            end_time = start_time + wait_time  # One minute later
            while current_date <= end_day:
                date_str = current_date.strftime('%Y-%m-%d')
                print(f"Processing date {date_str}")
                if request_counter >= requests_per_minute:
                    time_to_wait = end_time - time.time()
                    if time_to_wait > 0:
                        time.sleep(time_to_wait)
                    # Reset counter and update end_time to the next minute window
                    request_counter = 0
                    end_time = time.time() + wait_time
                    
                usage_headers = {
                    "method": "GET",
                    "authority": "api.openai.com",
                    "authorization": f"Bearer {openai_api_key}",
                    "openai-organization": openai_org_id,
                }
                usage_url = f"https://api.openai.com/v1/usage?date={current_date}&user_public_id={id_of_user}"
                usage_response = requests.get(usage_url, headers=headers)
                usage_data = usage_response.json()
                
                for entry in usage_data.get("data", []):
                    model_name       = entry.get("snapshot_id")  # Assuming 'snapshot_id' key contains the model name
                    prompt_token_cost, completion_token_cost = get_openai_api_pricing(model_name)
                    context_tokens   = entry.get("n_context_tokens_total", 0)
                    generated_tokens = entry.get("n_generated_tokens_total", 0)
                    entry_cost       = (context_tokens * prompt_token_cost / 1000) + (generated_tokens * completion_token_cost / 1000)
                    if model_name not in model_usage:
                        model_usage[model_name] = {
                            'total_generated_tokens': 0,
                            'total_context_tokens': 0,
                            'total_api_calls': 0,
                            'total_cost' : 0,
                            'daily_costs': {},
                            'daily_context_tokens': {},
                            'daily_generated_tokens': {},
                            'daily_api_calls': {},
                            'days_used': set()
                        }
                    model_usage[model_name]['total_generated_tokens'] += generated_tokens
                    model_usage[model_name]['total_context_tokens']   += context_tokens
                    model_usage[model_name]['total_api_calls']        += 1
                    model_usage[model_name]['total_cost']             += entry_cost
                    model_usage[model_name]['days_used'].add(current_date.strftime('%Y-%m-%d'))

                    add_daily_usage(model_usage, model_name,'daily_costs',entry_cost,date_str)
                    add_daily_usage(model_usage, model_name,'daily_context_tokens',context_tokens,date_str)
                    add_daily_usage(model_usage, model_name,'daily_generated_tokens',generated_tokens,date_str)
                    add_daily_usage(model_usage, model_name,'daily_api_calls',1,date_str)

                # Fixme: should track large images and small images instead of just images. cost calc is ok
                for entry in usage_data.get("dalle_api_data", []):
                    model_name   = entry.get("model_id")  # Assuming 'model_id' key contains the model name
                    image_small_cost, image_large_cost = get_openai_api_pricing(model_name)
                    num_images   = entry.get("num_images", 0)
                    num_requests = entry.get("num_requests", 0)
                    image_size   = entry.get("image_size", 0)
                    if(image_size == "1024x1024"):
                        cost_per_image = image_small_cost
                    else:
                         cost_per_image = image_small_cost
                    entry_cost       = num_images * cost_per_image
                    if model_name not in model_usage:
                        model_usage[model_name] = {
                            'total_images': 0,
                            'total_requests': 0,
                            'total_api_calls': 0,
                            'total_cost' : 0,
                            'daily_costs': {},
                            'daily_images': {},
                            'daily_requests': {},
                            'daily_api_calls': {},
                            'days_used': set()
                        }
                    model_usage[model_name]['total_images']           += num_images
                    model_usage[model_name]['total_requests']         += num_requests
                    model_usage[model_name]['total_api_calls']        += 1
                    model_usage[model_name]['total_cost']             += entry_cost
                    model_usage[model_name]['days_used'].add(current_date.strftime('%Y-%m-%d'))

                    add_daily_usage(model_usage, model_name,'daily_costs',entry_cost,date_str)
                    add_daily_usage(model_usage, model_name,'daily_images',num_images,date_str)
                    add_daily_usage(model_usage, model_name,'daily_requests',num_requests,date_str)
                    add_daily_usage(model_usage, model_name,'daily_api_calls',1,date_str)
 
                current_date += relativedelta(days=1)
                request_counter += 1
            user_summary = {
                "id":                     id_of_user,
                "name":                   name,
                "email":                  email,
                "model_usage": {model: {
                    key: (list(value) if isinstance(value, set) else value) 
                    for key, value in details.items()
                } for model, details in model_usage.items()}
            }
            print(f"email = {email}")
            print('Dump of user Summary: \n',json.dumps(user_summary, indent=4))
            user_results.append(user_summary)  # Append the result for the current user
        return json.dumps(user_results, indent=4)
    

    @staticmethod
    def describe_class( class_path: str) -> dict:
        """ Describe a class by listing its methods with details """

        def get_decorators(obj):
            """ Retrieve a list of decorators applied on a function """
            decorators = []

            # Attempt to get the wrapped function if it exists (common with decorators that use @wraps)
            while hasattr(obj, '__wrapped__'):
                decorators.append(obj.__wrapped__)
                obj = obj.__wrapped__

            # This handles more complex decorator scenarios and is just a basic placeholder
            # Actual implementation might need to handle specific decorator structures
            if not decorators:
                # Inspecting closure for functools.partial objects if no typical wrappers found
                if obj.__closure__:
                    closures = [c.cell_contents for c in obj.__closure__]
                    decorators.extend([
                        closure for closure in closures
                        if isinstance(closure, (functools.partial,))  # Checking for functools.partial used in decorators
                    ])

            return decorators
           
        def describe_function(function):
            """ Generate a description of the function including name, decorators, and arguments """
            signature = inspect.signature(function)
            decorators = get_decorators(function)
            decorator_names = [dec.__name__ if hasattr(dec, '__name__') else 'UnknownDecorator' for dec in decorators]
            return {
                'name': function.__name__,
                'decorators': decorator_names,
                'arguments': str(signature)
            }
        
        def get_class_from_string(class_path: str):
            """ Convert a string path to a class to a class object """
            module_path, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            return cls
    
        print(f"-------->Class Path: {class_path}")
        cls = get_class_from_string(class_path)

        methods = inspect.getmembers(cls, predicate=inspect.isfunction)
        method_descriptions = {method[0]: describe_function(method[1]) for method in methods} 
        return method_descriptions

