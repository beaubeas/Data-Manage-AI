import inspect
from typing import get_type_hints
import re
import traceback
from functools import wraps, partial
from typing import Callable, Optional, final
from pydantic import Field, computed_field
import random
import pickle

import pandas as pd
import rollbar

from pydantic import BaseModel
from langchain.agents import tool
from langchain_core.callbacks.manager import (
    adispatch_custom_event,
)

from supercog.shared.logging import logger
from supercog.shared.services import config, get_public_service_host
from supercog.shared.apubsub import RequestVarsEvent, ToolLogEvent, AssetTypeEnum

from .run_context import RunContext, LangChainCallback

# **The ToolFactory contract**
#
#
# When creating a new tool, follow these steps:
#
# 1. Define your tool class as a subclass of ToolFactory
# 2 Implement the __init__ method to call super.__init__ with id, system_name, auth_config, logo_url, and category
# 3. Implement the get_tools method to return a list of tool functions, calling 'self.wrap_tool_functions' to wrap them
# 4. Implement 'test_credentials' to verify that provided secrets are valid
# 
# When you functions are called, the following will be setup automatically:
#
# self.credentials - will be set to your tool secrets
# self.run_context - All "agent context" is available here, like agent_id, tenant_id, etc...

# Tool functions should return this if they DON'T want their results shrunk
class LLMFullResult(str):
    pass

class ToolConfigError(RuntimeError):
    pass

class ToolCategory:
    CATEGORY_GENAI    = "GenAI"
    CATEGORY_BUILTINS = "System Tools"
    CATEGORY_FILES    = "Files & Documents"
    CATEGORY_EMAIL    = "Email"
    CATEGORY_SPEECH   = "Speech"
    CATEGORY_DEVTOOLS = "Dev Tools"

    CATEGORY_SAAS     = "Connectors"
    CATEGORY_INTERNET = "Internet"
    CATEGORY_SECURITY = "Security"
    CATEGORY_LIVE     = "Live Info"
    CATEGORY_CALENDAR = "Calendar"
    CATEGORY_DOCSRC   = "Knowledge Sources"


class ToolFactory(BaseModel):
    id: str
    system_name: str
    # Set to the name of ANOTHER system which has compatiable credentials
    compatible_system: str = None
    auth_config: dict
    oauth_scopes: list[str] = []
    logo_url: str|None = None
    help: str|None = None
    category: str|None = None
    credentials: dict = {}
    inmem_state: dict = {}
    run_context: RunContext = Field(exclude=True, default=None)
    tool_uses_env_vars: bool = False
    lc_run_id: str|None = None
    is_docsource: bool = False
    class Config:
        arbitrary_types_allowed=True

    # ChatEngine should call this method to get the agent tools, since it may add additional
    # functions beyond what the underlying Tool classes explicitty declare.
    def _get_full_agent_tools(self) -> list[Callable]:
        tools = self.get_tools()
        if self.tool_uses_env_vars:
            tools.extend(
                self.wrap_tool_functions([
                    self.request_user_provide_env_vars,
                    self.check_for_env_vars,
                ])
            )
        return tools
    
    def get_tools(self) -> list[Callable]:
        return [self.get_tool()]

    @final    
    def get_tool(self) -> Callable:
        raise NotImplementedError("Only use 'get_tools' don't implement the singular.")

    def get_oauth_client_id_and_secret(self) -> tuple[str|None, str|None]:
        return None, None
    
    @computed_field
    def agent_functions(self) -> list[dict]:
        tool_funcs = sorted(self.get_tools(), key=lambda f: f.name)
        def get_docstring(f):
            if f.coroutine:
                return f.coroutine.__doc__ or ""
            else:
                return f.func.__doc__ or ""
        return [
            {"name":f.name,"help":get_docstring(f).strip()} for f in tool_funcs
        ]
    
    def _get_last_arg_type(self, func):
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        last_param = list(sig.parameters.keys())[-1]
        return type_hints.get(last_param, type(None))

    def _get_tool(self, tool_func) -> Callable:
        # This function wraps all tool functions in our wrapper for special handling:
        # - we catch errors and return them as strings
        # - we "shrink" results if they are too big
        # - we auto-add the Langchain "callbacks" arg so we can use it when we need the tool call run_id   
        if not tool_func.__doc__:
            print (f"Error: Tool function {tool_func.__name__} must have a docstring. Skipping.")
            return None
        myfunc = partial(self.return_error_as_string(tool_func))
        myfunc.__name__ = tool_func.__name__
        myfunc.__doc__ = tool_func.__doc__
        # Keep the original arg list
        myfunc.__annotations__ = tool_func.__annotations__
        if 'callbacks' not in myfunc.__annotations__:
            # This is some foo to "jam" the callbacks param that Langchain expects so that we receive
            # it in our wrapper function and can set it as `lc_run_id` when the function is called.
            myfunc.__annotations__['callbacks'] = LangChainCallback
            old_sig = inspect.signature(myfunc)
            new_param = inspect.Parameter('callbacks', inspect.Parameter.KEYWORD_ONLY, 
                                        annotation=LangChainCallback, default=None)
            new_params = list(old_sig.parameters.values()) + [new_param]
            myfunc.__signature__ = old_sig.replace(parameters=new_params)

        t = tool(myfunc)
        t.handle_validation_error = True
        return t


    # This crazy little function is wrapping ALL tool functions. It catches errors, returning
    # them as strings to the LLM. It also shrinks results if they are too big.
    # Finally, it attempts to always accept the "callbacks" parameter from LangChain
    # and to setup the lc_run_id attribute so that we can link tool events to their tool call parent.
    def return_error_as_string(self, tool_func):

        def format_exc(e):
            if isinstance(e, ToolConfigError):
                return f"Tool error: {e}"
            tb = e.__traceback__        
            # Format the traceback and get the last 3 frames
            formatted_tb = traceback.format_tb(tb)[-3:]
            # Join the formatted traceback frames into a single string
            formatted_tb_str = ''.join(formatted_tb)
            return f"Error: {e}\n" + formatted_tb_str
        
        if inspect.iscoroutinefunction(tool_func):
            async def wrapped_async_func(*args, callbacks: LangChainCallback|None=None, **kwargs):
                self.lc_run_id = str(callbacks.parent_run_id) if callbacks else None

                if callbacks is None:
                    rollbar.report_message("LC callbacks is blank", extra_data={"func":str(tool_func)})
                elif self.lc_run_id is None:
                    rollbar.report_message("LC run Id is blank", extra_data={"func":str(tool_func)})

                try:
                    if 'callbacks' in inspect.signature(tool_func).parameters:
                        kwargs['callbacks'] = callbacks
                    return self.shrink_tool_result(await tool_func(*args, **kwargs))
                except Exception as e:
                    return format_exc(e)
            return wraps(tool_func)(wrapped_async_func)
        else:
            def wrapped_func(*args, callbacks: LangChainCallback|None=None, **kwargs):
                self.lc_run_id = str(callbacks.parent_run_id) if callbacks else None

                if callbacks is None:
                    rollbar.report_message("LC callbacks is blank", extra_data={"func":str(tool_func)})
                elif self.lc_run_id is None:
                    rollbar.report_message("LC run Id is blank", extra_data={"func":str(tool_func)})
                try:
                    if 'callbacks' in inspect.signature(tool_func).parameters:
                        kwargs['callbacks'] = callbacks
                    return self.shrink_tool_result(tool_func(*args, **kwargs))
                except Exception as e:
                    return format_exc(e)
            return wraps(tool_func)(wrapped_func)

    def shrink_tool_result(self, result):
        if isinstance(result, LLMFullResult):
            return result

        # Auto-convert lists of dicts into dataframes
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            result = pd.DataFrame(result)
            return self.get_dataframe_preview(result)       

        if isinstance(result, dict) and 'type' in result:
            return result # assume dataframe preview or similar
        
        max_string_size = 2000

        str_val = str(result)
        if len(str_val) > max_string_size: # approx 500 tokens
            var_name = self.make_dataframe_name("preview_")
            self.inmem_state[var_name] = result
            self.run_context.queue_asset_event(
                var_name, 
                AssetTypeEnum.DOC, 
                var_name,
                content=str(result),
                content_type="text/plain"
            )

            return {
                "type": "preview",
                "name": var_name,
                "result": str(result)[0:max_string_size],
                "length": len(result),                
            }
        else:
            return result

    def wrap_tool_functions(self, tool_funcs: list[Callable]) -> list[Callable]:
        if not isinstance(tool_funcs, list):
            tool_funcs = [tool_funcs]
        return list(filter(lambda x: x is not None, [self._get_tool(tool_func) for tool_func in tool_funcs]))
    
    def is_tool_ready(self) -> tuple[bool, str]:
        # Indicates if the tool is configured and ready to use
        return True, ""

    def make_dataframe_name(self, name_hint: str|None = None):
        if name_hint:
            if "." in name_hint:
                name_hint = name_hint.split(".")[0]
            name_hint = re.sub(r'\W|^(?=\d)', '_', name_hint).replace(" ","_") + "_dataframe"
        else:
            name_hint = "dataframe_"

        if name_hint in self.inmem_state:
            return f"{name_hint}_{random.randint(1000, 9999)}"
        else:
            return name_hint
    
    def get_dataframe_preview(self, df: pd.DataFrame, max_rows=5, name_hint:str|None=None,
                              sanitize_column_names=True) -> dict:
        row_label = "all_rows"
        includes_all = True
        if df.shape[0] > max_rows:
            row_label = "preview"
            includes_all = False

        preview_rows = df.head(max_rows).astype(str).values.tolist()
        name = self.make_dataframe_name(name_hint)

        if sanitize_column_names:
            newnames = {}
            for col in df.columns.tolist():
                newname = col.lower().replace(r"\s+", "_")
                newnames[col] = newname
            df.rename(columns=newnames, inplace=True)
        
        if not name_hint:
            name_hint = ""

        self.inmem_state[name] = df
        self.run_context.queue_asset_event(
            "dataframe:" + name,
            AssetTypeEnum.TABLE,
            name,
            pickle.dumps(df),
            content_type="application/pickle",
        )
        if includes_all:
            hint = {}
        else:
            hint = {"hint": "On request, use load_full_preview_content to get all rows"}

        return {
            "type":"dataframe",
            "name": name,
            "source_file": name_hint,
            "columns": df.columns.tolist(),
            "row_count": df.shape[0],
            row_label: preview_rows,
            
        } | hint

    def get_dataframe_from_handle(self, handle: any) -> tuple[pd.DataFrame, str]:
        if isinstance(handle, str) and handle in self.inmem_state:
            return self.inmem_state[handle], handle
        elif isinstance(handle, dict) and 'name' in handle:
            name = handle['name']
            return self.inmem_state[name], name
        else:
            raise RuntimeError(f"Could not find dataframe '{handle}'")

    def get_data_from_handle(self, handle: any) -> any:
        if isinstance(handle, str) and handle in self.inmem_state:
            return self.inmem_state[handle]
        elif isinstance(handle, dict) and 'name' in handle:
            name = handle['name']
            return self.inmem_state[name]
        else:
            raise RuntimeError(f"Could not find variable '{handle}'")

    def logo_from_domain(self, domain: str) -> str:
        return f"https://logo.clearbit.com/{domain}"

    def logo_from_company_name(self, company_name: str) -> str:
        domain = f"https://company.clearbit.com/v1/domains/find?name=:{company_name}name"
        return f"https://logo.clearbit.com/{domain}"
    
    def prepare_creds(self, cred, secrets: dict) -> dict:
        """
            This function allows a tool to "refresh" its credential secrets before
            we use it. Oauth tools can refresh their tokens and they should
            call Credential.refresh_oauth_tokens so that they new tokens are 
            stored for next time. Then they can return the new values.
        """
        return secrets

    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """
        return str("Test credentials is not implemented")

    async def log(self, *msgs, callbacks: LangChainCallback=None):
        message=''.join(map(str, msgs)) + "  \n"
        agevent = self.run_context.create_event(ToolLogEvent, callbacks, message=message)
        await adispatch_custom_event(
            agevent.type,
            agevent.model_dump(),
        )   

    def dataframe_batch_iterator(self, df, batch_size):
        for start in range(0, len(df), batch_size):
            yield df.iloc[start:start + batch_size]

    async def request_user_provide_env_vars(
            self, 
            var_names: list[str], 
            update_existing: bool = False,
            callbacks: LangChainCallback=None) -> str:
        """" Request the user to provide the required ENV VARs. """

        vars_needed = [var for var in var_names if update_existing or self.run_context.get_env_var(var) is None]

        if len(vars_needed) > 0:
            agevent = self.run_context.create_event(RequestVarsEvent, callbacks, var_names=vars_needed)
            await adispatch_custom_event(
                agevent.type,
                agevent.model_dump(),
            )
            return "Wait for confirmation that these variables have been set."
        else:
            return "Requested vars already set."
        

    def check_for_env_vars(self, var_list: list[str]) -> str:
        """ Checks that the indicate ENV VARs are set properly. """
        missing = []
        for var in var_list:
            if not self.run_context.get_env_var(var):
                missing.append(var)

        if missing:
            return f"Error: The following ENV VARs are missing: {', '.join(missing)}"
        else:
            return "Var is set."

    def get_callback_url(self, dashboard_path, tenant_id, user_id, **kwargs) -> str:
        host = get_public_service_host("dashboard")
        
        # We should probably encode tenant and user id into "state" and double check on the callback.

        # Build redirect URL with the index ID parameter
        # add kwargs as url params, generically
        redirect_path = f"/{dashboard_path}"
        if kwargs:
            redirect_path += "?" + "&".join([f"{k}={v}" for k, v in kwargs.items()])
        return f"{host}{redirect_path}"




import json
import os
import dill
dill.settings['recurse'] = True  # Tell dill to attempt to serialize objects recursively

from types import FunctionType
from inspect import getmembers, isfunction
from supercog.engine.filesystem import SYSTEM_ROOT_PATH, unrestricted_filesystem

class ToolRegistry:
    """ This class is for dynamic creation or loading of tools """
    dynamic_tools_directory = ""
    
    def __init__(self):
        self.registered_tools = {}

    def register_tool(self, file_name: str, class_name: str, static_code: str, loading_flag: bool):
        """
        Registers a dynamic (for noew) tool by creating an instance of the already created tool
        from the tool class or using the passed instance. 
        
        Args:
            class_name (type | instance): The class or instance of the tool to be registered.
                                          If it's a class, an instance will be created from it.
            loading_flag (bool): Indicates whether the tool is being loaded from the filesystem on startup
                                 (True) or is being dynamically created during runtime (False).
                                 When set to False, the tool is serialized to the filesystem for
                                 persistence.
        Description:
            This method checks if the passed tool_class is an actual class type and creates an instance if so.
            It then registers the tool in both a local dictionary for runtime access and a global list for
            persistent storage if needed. It also handles the serialization of newly created tools when not
            loading, to ensure they are available on subsequent application starts.
        """
        from .all_tools import TOOL_FACTORIES, FACTORY_MAP


        # If we are creating this tool (from the toolBuilder Agent) then
        # write this tool to the filesystem to read it in on next  supercog start.
        # If instead we are just loading this tool on initial start, skip this

        with unrestricted_filesystem():
            if not loading_flag:
                self._serialize_to_file( static_code, class_name)
            try:
                tool_class =self._deserialize_from_file(file_name, class_name)
            except Exception as e:
                error_msg = f"Failed to load dynamic class {class_name}. Error: {e}"
                logger.error(error_msg)
                return
        # Determine if the tool_class is a class and create an instance if so
        if isinstance(tool_class, type):
            try:
                instance = tool_class()  # Create an instance if it's a class
            except Exception as e:
                error_msg = f"Failed to load dynamic class {class_name}. Error: {e}"
                logger.error(error_msg)
                return
            print(f"Creating and registering instance of class {tool_class.__name__}")
            class_to_serialize = tool_class  # Store the class for serialization
        else:
            instance = tool_class
            class_to_serialize = tool_class.__class__  # Get the class of the instance
            print(f"Registering instance of {class_to_serialize.__name__}")


        print(f"Registering instance id {instance.id} with system_name {instance.system_name}")
        self.registered_tools[instance.id] = instance
        
        # Check: if the tool is already registered, then update else add new
        existing_tool = next((tool for tool in TOOL_FACTORIES if tool.id == instance.id), None)
        if existing_tool:
            # Update the existing tool entry
            existing_index = TOOL_FACTORIES.index(existing_tool)
            TOOL_FACTORIES[existing_index] = instance
            FACTORY_MAP[instance.id] = instance
            print(f"Updated existing tool: {instance.id}")
        else:
            # Add new tool to the list and map
            TOOL_FACTORIES.append(instance)
            FACTORY_MAP[instance.id] = instance
            print(f"Added new tool: {instance.id}")

        # If we are creating this tool (from the toolBuilder Agent) then
        # write this tool to the filesystem to read it in on next  supercog start.
        # If instead we are just loading this tool on initial start, skip this
        if not loading_flag:
            with unrestricted_filesystem():
                self._serialize_to_file( static_code, instance.id)
                
        # Debugging: Print all tools in TOOL_FACTORIES
        logger.debug("Current Tools in TOOL_FACTORIES:")
        for tool in TOOL_FACTORIES:
            logger.debug(f"Tool ID: {tool.id}, Tool Name: {tool.system_name}")
        return instance

    def _check_filesystem_registry(self):
        """
        Check if the registry directory exists, and create it if it doesn't.
        This will be called as a result of the load_tool_factories call from
        the dashboard. Kind of an initial load time.
        So the first time this runs in a system without dynamic tools,
        the directory to hold them will be created.
        """
    
        # Check if the directory exists
        if not os.path.exists(self.dynamic_tools_directory):
            # Create the directory if it doesn't exist
            os.makedirs(self.dynamic_tools_directory)

    def _serialize_to_file(self, class_code,class_name: str):
        """
        Serializes Python code to a Python source file within the 'tool_registry' directory. 
        The provided code should be a complete Python class in string format.

        Args:
            class_code (str): The complete Python code as a string.
            file_name (str): The name of the file (without extension) to save the code.
        """
        filepath = os.path.join(self.dynamic_tools_directory, f"{class_name}.py")
        with open(filepath, 'w') as file:
            file.write(class_code)
        print(f"Serialized class to {filepath}")



    def _deserialize_from_file(self, file_name: str, class_name: str):
        
        """
        Deserializes a Python class from a Python source file located within the 'tool_registry' directory
        by dynamically loading it as a module.

        Args:
            file_name (str): The name of the file (without extension) that contains the Python code.

        Returns:
            The Python class object extracted from the loaded module.
        """
        import importlib.util
        import sys
        filepath = os.path.join(self.dynamic_tools_directory, file_name)
        module_name = os.path.splitext(os.path.basename(filepath))[0]
        print(f"-----> _deserialize_from_file:  module_name = {module_name}")
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if class_name in module.__dict__:
            obj = module.__dict__[class_name]
            if isinstance(obj, type):  # Ensure it is a class
                print(f"Deserialized class {class_name} from {file_name}")
                return obj
        raise ImportError(f"Class {class_name} not found in {file_name}")

    def load_registry_from_filesystem(self, tenant_id: str = None):
        """
        Load registry from files in the 'tool_registry' directory.
        """

        if 'SUPERCOG_LOCAL_TOOLS' in os.environ:
            self.dynamic_tools_directory = os.environ['SUPERCOG_LOCAL_TOOLS']
            print(f"Looking for local tools in: {self.dynamic_tools_directory}")
        elif tenant_id is not None:
            self.dynamic_tools_directory = os.path.join(SYSTEM_ROOT_PATH, tenant_id, 'tool_registry')
        else:
            logger.warn("Can't load tools, tenant_id not yet known")
            return

        # Get the list of files in the directory
        self._check_filesystem_registry()
        files = os.listdir(self.dynamic_tools_directory)

        # Deserialize each file
        for file_name in files:
            if file_name.endswith('.py'):
                print(f"Deserializing tool: {file_name}")
                # Assuming .py extension for serialized files
                # Search the source code to extact the class name
                with open(os.path.join(self.dynamic_tools_directory, file_name), 'r') as file:
                    code = file.read()
                    # Extract the class name from the code
                    m = re.search('class ([^\(]*)', code)
                    if m:
                        class_name = m.group(1)
                        # Register the tool with the extracted class name
                        self.register_tool(file_name, class_name, {"code":""}, True)
                    else:
                        print(f"Error! Found no class declaration in: {file_name}")
            
    def get_tool(self, tool_id):
        return self.registered_tools.get(tool_id)

TOOL_REGISTRY = ToolRegistry()
# would be lovely to do this at load time like below, but we don't know the tenant_id yet.


'''
This is the json attempt at serialize/deserialize
    @staticmethod
    def serialize_to_file( obj: BaseModel, file_path: str):
        """Serialize a Pydantic model object to a JSON file.
           The assumpiton is that this will be run by the
           Dynamic_tool_builder Agent and will be run under 
           the Agent_filesystem.
        """
        class_attrs = {}
        for name, attr in getmembers(obj.__class__):
            if not name.startswith("__"):
                class_attrs[name] = attr
        obj_dict = obj.dict()
        file_path = os.path.join('tool_registry', file_path)
        with open(file_path, 'w') as file:
            json.dump({'class_attrs': class_attrs, 'data': obj_dict}, file)
        
 @staticmethod
    def deserialize_from_file( file_path: str):
        """Deserialize a Pydantic model object from a JSON file."""
        file_path = os.path.join('tool_registry', file_path)
        with open(file_path, 'r') as file:
            data = json.load(file)
        class_attrs = data['class_attrs']
        class_name = class_attrs['__name__']
        base_classes = (BaseModel)
        if '__bases__' in class_attrs:
            base_classes += tuple(class_attrs['__bases__'])
        cls = type(class_name, base_classes, class_attrs)
        obj = cls(**data['data'])
        return obj
'''

'''
    def _serialize_to_file(self, cls, file_path: str):
        """
        Serializes a dynamically created class to a binary file using the dill library. This function
        captures the class's name, its base classes, and its attributes (excluding non-serializable
        Python-specific attributes like __dict__ and __weakref__), allowing the class to be
        reconstructed later from this serialized form.

        Args:
            cls (type): The dynamically created class to be serialized. This class should be
                        an instance of type that potentially includes dynamically added attributes and methods.
            file_path (str): The path within the 'dynamic_tools_directory' where the serialized
                             data should be stored. This path is appended to the 'dynamic_tools_directory'
                             to form the full path to the file.

        Notes:
            The serialized file will be stored in binary format and includes detailed class structure
            data to enable precise reconstruction of the class when deserialized. The full file path
            is constructed by combining the provided 'file_path' with the 'dynamic_tools_directory'.
        """
        class_data = {
            'name': cls.__name__,
            'bases': cls.__bases__,
            'dict': {key: value for key, value in cls.__dict__.items() if key not in ('__dict__', '__weakref__')}
        }
        full_file_path = os.path.join(self.dynamic_tools_directory, file_path)
        with open(full_file_path, 'wb') as file:
            cloudpickle.dump(class_data, file)

    @staticmethod
    def _deserialize_from_file(file_path: str):
        """
        Deserializes a dynamically created class from a binary file using the dill library.
        This function reads the binary file, extracts the class data, and reconstructs the class
        using this data. The reconstructed class will have the same name, base classes, and attributes
        as the original serialized class.

        Args:
            file_path (str): The full path to the file containing the serialized class data. This path
                             should include the 'dynamic_tools_directory' if it was used during serialization.

        Returns:
            type: The reconstructed class, which can then be instantiated or used as needed.

        Notes:
            The file is expected to be in binary format and contain serialized data that includes the class's
            name, its base classes, and a dictionary of attributes. The reconstruction involves creating a new
            type object using these components.
        """
        with open(file_path, 'rb') as file:
            #return  cloudpickle.load(file)
            class_data = cloudpickle.load(file)
            return type(class_data['name'], class_data['bases'], class_data['dict'])
'''
