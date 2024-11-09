from typing import Any
import pytest

from langchain_community.tools.tavily_search.tool import TavilySearchResults
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain import hub
from langchain.agents import create_tool_calling_agent
from langchain.agents import AgentExecutor
from langchain.agents import tool
from langchain.callbacks.base import BaseCallbackHandler

from supercog.engine.chatengine import InterruptableAgentExecutor

@tool
def get_time():
    """ returns the current time """
    from datetime import datetime
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    return current_time


search_added: bool = False


# Get the prompt to use - you can modify this!
@pytest.mark.asyncio
async def test_dynamic_tools():
    search = TavilySearchResults(max_results=2)

    @tool
    def joke_maker() -> str:
        """ returns a joke about the weather """
        return "The coldest winter I ever spent was a summer in San Francisco."
    
    @tool
    async def activate_tool(tool_name: str):
        """ activates a tool, either 'weather' or 'joke_maker'. """
        print("!! REQUEST TO ACTIVATE TOOL: ", tool_name)
        if tool_name == 'weather':
            await agent_executor.add_tools([search])
        elif tool_name == 'joke_maker':
            await agent_executor.add_tools([joke_maker])
        return f"the {tool_name} tool has been enabled."

    tools = [get_time, activate_tool]

    model = ChatOpenAI(model="gpt-4o-mini")

    prompt = hub.pull("hwchase17/openai-functions-agent")
    prompt.messages

    agent = create_tool_calling_agent(model, tools, prompt)
    agent_executor = InterruptableAgentExecutor(agent=agent, tools=tools)

    output = ""
    async for event in agent_executor.astream_events(
        {
            "input": "Check the weather in SF today. If it looks cold then request a joke about the weather.",
        },
        version="v2",
    ):
        if event['event'] == "on_chat_model_stream":
            output += event['data']['chunk'].content
        else:
            if output:
                print("[OUTPUT >>] ", output)
                output = ""
            if event['event'].startswith("on_tool"):
                print(f"[{event['event'].upper()} >>]: {event}")
            else:
                print(f"[{event['event'].upper()} >>]: {str(event)[0:80]}")
    if output:
        print(output)
    


