from supercog.engine.tool_factory import ToolFactory, ToolCategory, TOOL_REGISTRY
from supercog.shared.services import config

from   typing import List, Callable
import json
import inspect
import types
from   types import FunctionType, CodeType

class DynamicToolBuilder(ToolFactory):
    openai_api_key: str = ""

    def __init__(self):
        super().__init__(
            id="dynamic_tool_builder_connector",
            system_name="Dynamic Tool Builder",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/2/24/Logo_ToolboX_SVG.svg",
            auth_config={
                #"strategy_token": {
                #    "openai_api_key": "API KEY - find this at https://platform.openai.com/api-keys",
                #    "help": "Create an OpenAI API key and set the value here."
                #}
            },
            category=ToolCategory.CATEGORY_DEVTOOLS,
            help="""
Use this tool to help build tools dynamically
"""
        )

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            self.create_dynamic_tool,
            self.view_created_tool,
        ])
    
    @staticmethod
    def _create_method(name, code):
        # Compile the code as a single function definition
        compiled_code = compile(code, '', 'exec')

        # Extract the function object from the compiled code
        func_code = [const for const in compiled_code.co_consts if isinstance(const, CodeType)][0]
        return FunctionType(func_code, globals(), name)
    
    def _create_tool_class(self, name, base=ToolFactory, attributes=None, methods=None):
        """
        Dynamically create a tool class with given attributes and methods.

        :param name:       str -         Name of the class to create.
        :param base:       ToolFactory - Base class for the new class.
        :param attributes: dict -        Dictionary of attributes to add to the class.
        :param methods:    dict -        Dictionary of method names and their code as strings.
        :return:           type -        New dynamically created class.
        """
        self.openai_api_key = self.credentials.get('openai_api_key', config.get_global("OPENAI_API_KEY"))

        if attributes is None:
            attributes = {}
        if methods is None:
            methods = {}

        # Create a new class dictionary
        cls_dict = {'__annotations__': {}}

        # Add all attributes to the class dictionary with annotations
        for attr_name, attr_value in attributes.items():
            # Determine the type of the attribute for annotation
            attr_type = type(attr_value)
            cls_dict['__annotations__'][attr_name] = attr_type
            cls_dict[attr_name] = attr_value

        # Dynamically add methods to the class
        for method_name, method_body in methods.items():
            method = DynamicToolBuilder._create_method(method_name, method_body)
            cls_dict[method_name] = method

        # Create the class using type()
        cls = type(name, (base,), cls_dict)
        cls.__module__ = 'dynamic_module'
        #ToolClass = self._create_tool_class(name,ToolFactory,attributes,methods)
        #TOOL_REGISTRY.register_tool(ToolClass, source_code, False)
        return cls

    def create_dynamic_tool(self,
                            name:        str,
                            id:          str,
                            source_code: str,
                            ) -> dict:
        """
        Dynamically creates and registers a tool with specified attributes and methods.

        Args:
            name (str):         Name of the tool class.
            id (str):           unique identifier for the tool
            source_code (str):  Source code representing the complete tool class.
        Returns:
            dict: Results of the tool creation process, including status and messages.o
        """
        print(f"create_tool called w:\nName: {name}\nid: {id}\n source_code", json.dumps(source_code))
        TOOL_REGISTRY.register_tool(name, name, source_code, False)
        #FIXME:  !!! it would be nice here to add the tool just created to the agent that asked
        #            that it be created. Especially if the LLM tried to create the tool.
        return {"function": "DynamicToolBuilder.create_tool",
                "status":   "success",
                "message":  f"Created the tool {name}."}

        
    def view_created_tool(self, id: str) -> dict:
        """
        Retrieves and displays the source code and documentation for a
        tool identified by its unique ID.

        Args:
            id (str): The unique identifier for the tool.

        Returns:
            dict: A dictionary containing the tool's attributes and methods,
                  including source code and documentation.
        """
        from supercog.engine.all_tools import TOOL_FACTORIES, FACTORY_MAP
        
        # Get all attributes of the ToolFactory instance
        tool_instance = FACTORY_MAP[id]
        tool_class_name = tool_instance.__class__.__name__
        print(f"tool Name: {tool_class_name}")
        # Get all members of the class
        #members = inspect.getmembers(ToolFactory)
        #members = inspect.getmembers(tool_instance, predicate=inspect.isfunction)
        members = []
        for attr_name, attr_value in inspect.getmembers(tool_instance):
            if inspect.ismethod(attr_value) or inspect.ismethoddescriptor(attr_value):
                members.append((attr_name, attr_value))
        # Filter out callable members (methods) and retrieve their source code
        methods = {}
        
        for name, member in members:
            print(f"Name: '{name}' ")
            if hasattr(member, '__qualname__'):
                print(f"qualname: '{member.__qualname__}'")
                if  member.__qualname__.split('.')[0] == tool_class_name:
                    source_code = inspect.getsource(member)
                    methods[name] = {
                        "source_code": source_code,
                        "docstring": inspect.getdoc(member),
                    }
        attributes = dict(tool_instance)

        # Create a dictionary containing both attributes and methods
        attributes_and_methods_dict = {
            "attributes": attributes,
            "methods": methods
        }

        # Print the dictionary
        return(attributes_and_methods_dict)

"""
 for name, member in members
            if hasattr(member, '__qualname__'):
                print(f"Name: {name} qualname: {member.__qualname__}")
                if inspect.isfunction(member):
                   if name == member.__qualname__
____
 for name, member in members:
            if inspect.isfunction(member) and hasattr(member, '__self__'):
                owner_class = member.__self__.__class__
                print(f"Owner class: {dict(owner_class)}")
                if owner_class == type(tool_instance):
                    source_code = inspect.getsource(member)
                    methods[name] = source_code
"""
