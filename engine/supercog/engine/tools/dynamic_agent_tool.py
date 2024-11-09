import re
from typing import Callable

from openai import OpenAI

from supercog.shared.services import config
from supercog.shared.apubsub import AddMemoryEvent, EnableToolEvent, ChangeStateEvent
from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback

class DynamicAgentTool(ToolFactory):
    def __init__(self, **kwargs):
        if kwargs:
            super().__init__(**kwargs)
        else:
            super().__init__(
                id = "dynamic_agent_tools",
                system_name = "Dynamic Agent Functions",
                logo_url="/bolt-icon.png",
                auth_config = { },
                category=ToolCategory.CATEGORY_BUILTINS,
                help="""
    Enable agent to lookup and enable tools dynamically
    """
            )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.save_memory,
            self.get_available_system_tools,
            self.search_for_tool,
            self.enable_agent_tool,
        ])
       
    async def save_memory(self, fact: str, callbacks: LangChainCallback) -> str:
        """ Adds a new fact to our long-term memory. Only call this function if you are SURE
            that this fact is important to remember. """
        
        if len(fact) > 1000:
            return "Error: The fact is too long. Please keep it under 1000 characters."
        
        await self.run_context.publish(
            self.run_context.create_event(AddMemoryEvent, callbacks, fact=fact)
        )

        return "The fact was saved into memory."

    async def get_available_system_tools(self) -> str:
        """" Returns the list of tools that can be enabled for the agent. """
        from supercog.engine.all_tools import TOOL_FACTORIES
        return ", ".join([t.system_name for t in TOOL_FACTORIES])

    async def search_for_tool(self, purpose: str) -> list[str]:
        """ Searches for one or more tools related to the indicated purpose. """
        from supercog.engine.all_tools import TOOL_FACTORIES

        client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))

        SEARCH_PROMPT = (
            f"Given the list of tools below, return one or two suggestions for the tool that best fits: {purpose}.\n" +
            "Only return the exact names of the tool, comma separated, or NONE if no tool fits the purpose.\n" +
            "----------" +
            await self.get_available_system_tools()
        )
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": SEARCH_PROMPT}
        ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={ "type": "text" },
        )
        result = response.choices[0].message.content
        print("Tool search result choices: ", result)
        if result is None or "NONE" in result:
            # simple keyword search
            purpose2 = purpose.replace("tool", "").lower().strip()
            candidates = [t.system_name for t in TOOL_FACTORIES if (
                purpose in t.system_name.lower() or purpose2 in t.system_name.lower()
            )]
            if len(candidates) > 0:
                # sort candidates by longest name first
                candidates.sort(key=lambda x: len(x), reverse=True)
                result = ", ".join(candidates[:2])

        return (result or "NONE").split(",")

    async def enable_agent_tool(self, tool_name: str, callbacks: LangChainCallback) -> str:
        """ Enables the AI agent to use the tool with the indicated name. """
        from supercog.engine.all_tools import TOOL_FACTORIES
        
        # Remove use of 'tool' word in the tool name. Use regexp
        # to match. And lowercase.
        tool_name1 = tool_name.lower()
        tool_name2 = re.sub(r"\s+tool\s*", "", tool_name.lower())

        for tool in TOOL_FACTORIES:
            if tool.system_name.lower() in [tool_name1, tool_name2]:
                if self.run_context.tool_is_enabled(tool.id):
                    return f"Note: The tool {tool.system_name} is already enabled"
                
                await self.run_context.publish(
                    self.run_context.create_event(
                        EnableToolEvent, callbacks, tool_factory_id=tool.id, name=tool.system_name
                    )
                )
                return f"The tool {tool.system_name} has been enabled."
        else:
            return f"Error: Tool not found: {tool_name}."
