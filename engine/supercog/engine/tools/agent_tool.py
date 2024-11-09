import re
from functools import partial
from typing import Callable, Any, Optional

from langchain.callbacks.manager import (
    AsyncCallbackManager
)
from langchain.agents import tool

from supercog.engine.tool_factory import ToolFactory, ToolCategory

class AgentTool(ToolFactory):
    target_agent_id: Optional[str] = None
    
    def __init__(self):
        super().__init__(
            id = "agent_tool",
            system_name = "Call Agent",
            auth_config = {},
            logo_url="https://www.boostability.com/content/wp-content/uploads/sites/2/2021/02/Feb.-17-Bots-e1614642771145.jpg",
            category=ToolCategory.CATEGORY_BUILTINS,
            help="""
Use this tool to invoke another agent from your current agent.
"""
        )

    def get_tools(self, target_agent_id: str, target_agent_name: str) -> list[Callable]:
        """ Synthesizes a tool function named after the Agent we want to call. This func will be bound
            to the calling agent.
        """
        self.target_agent_id = target_agent_id

        tool_func = self.run_target_agent

        myfunc = partial(tool_func)
        sanitized = re.sub(r'\W|^(?=\d)', '_', target_agent_name.lower()).replace(" ","_")
        fname = "invoke_" + sanitized + "_agent"
        myfunc.__name__ = fname
        myfunc.__doc__ = f"Call the '{target_agent_name}' agent and return its results"
        # Keep the original arg list
        myfunc.__annotations__ = tool_func.__annotations__
        return [tool(myfunc)]
    
    async def run_target_agent(
        self,
        prompt: str,
        callbacks: Optional[AsyncCallbackManager]=None,
        ) -> str:
        # The callbacks value will contain the Langchain "run id" which we need to include in our events
        # (as 'lc_run_id') so that we can associate events from this function call with the right invocation
        # in the caller.

        return await self.run_context.execute_agent(
            self.target_agent_id, 
            prompt, 
            callbacks
        )
