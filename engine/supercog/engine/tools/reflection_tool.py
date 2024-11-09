import asyncio
import requests
import json

from fastapi import FastAPI, Depends, HTTPException, Path, status

from supercog.shared.services    import config, serve, db_connect
from supercog.shared.models      import RunCreate, AgentBase
from supercog.shared.pubsub      import pubsub
from supercog.shared.logging     import logger
from supercog.shared.credentials import secrets_service
from supercog.engine.triggerable import Triggerable
from supercog.shared.services    import get_service_host

from sqlmodel import SQLModel, Field, Session, create_engine, select

from supercog.engine.db           import session_context
from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback
from supercog.shared.services     import config, db_connect


from pytz import utc
from typing import Any, Callable, Optional

from openai import OpenAI
import json
import re


BASE = get_service_host("engine")



class ReflectionTool(ToolFactory):
    credentials: dict = {}

    def __init__(self):
        super().__init__(
            id = "reflection",
            system_name = "Reflection",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/9/92/Rodin_TheThinker.jpg",
            category=ToolCategory.CATEGORY_BUILTINS,
            help="""
Use to instruct the LLM to reflect on it's actions and learn from them.
""",
            auth_config = {
             },
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.reflect,
            self.learn, 
        ])
    
    def reflect(self) -> str:
        """
        Using the current context from the previous run(s) and output,
        Ask the LLM to reflect on the last run and fix any errors
        """
        return ""
    
    def learn(self) -> str:
        """
        OK, we got some result from the LLM after reflection or from an error.
        It may be worthy of learning from.
        Ideally what we want is to learn in associative memory so Agents with
        simalar make up (their tools are the same or overlap, and their instructions
        are in the same general area) can look this scenario up and see how to
        avoid any errors and proceed in the best fashion. That thing worthy
        of learning may be the result of a reflection (some text returned by
        the LLM), or it may be the error message itself.

        For this first implementation we will just add the reflection to the
        context. At a later date we will save the reflection keyed by the
        context and agent configuration in a RAG database of some sort.
        """
        return ""
    
class ReflectionTriggerable(Triggerable):
    def __init__(self, agent_dict: dict, run_state) -> None:
        super().__init__(agent_dict, run_state)
        self.max_tries = 5 # default to 5 for max retries
        self.current_run = 1

    @classmethod
    def handles_trigger(cls, trigger: str) -> bool:
        return trigger.startswith("Reflection")
    
    def parse_and_strip_trigger_arg(self):
        # Extract the number after 'Max Tries:'
        match = re.search(r"Max Tries:\s*(\d+)", self.trigger_arg)
        if match:
            max_tries = int(match.group(1))
            # Remove 'Max Tries: n' from the string
            self.trigger_arg = re.sub(r"Max Tries:\s*\d+", '', self.trigger_arg).strip()
            return max_tries, self.trigger_arg
        else:
            return 5, self.trigger_arg  # default to 5 for max retries
        
    async def create_run(self) -> dict:
        """
        create_run will post to the agent service to run this agent
        Keyword arguments:
        reflection_instructions -- The reflection instructions for each time thorugh the loop.
        """
        self.max_tries, reflection_instructions = self.parse_and_strip_trigger_arg()
        run_data = {
                "tenant_id":      self.tenant_id + "",
                "user_id":        self.user_id + "",
                "agent_id":       self.agent_id,
                "input_mode":     "truncate",
                "input":          reflection_instructions,
                "result_channel": "test_results",
                "logs_channel":   "test_logs",
        }
        call_dump = json.dumps(run_data)
        print( f"Calling Agent service  reflect {call_dump}")
        response = requests.post(BASE + "/runs", json=run_data)
        return response.json()
    
    async def run(self):
        # Poll for events and dispatch them (run agents)

        while self.current_run < self.max_tries:
            result = await self.create_run()
            result_str = json.dumps(result)
            print( f"Calling Agent service  reflect {call_dump}")
            break
            
        return result


    def pick_credential(self, credentials) -> bool:
        return True


