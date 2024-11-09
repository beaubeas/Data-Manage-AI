from operator import itemgetter

from langchain.output_parsers import JsonOutputToolsParser
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


@tool
def count_emails(last_n_days: int) -> int:
    """Multiply two integers together."""
    return last_n_days * 2


@tool
def send_email(message: str, recipient: str) -> str:
    "Add two integers."
    return f"Successfully sent email to {recipient}."


tools = [count_emails, send_email]
model = ChatOpenAI(model="gpt-3.5-turbo", temperature=0).bind_tools(tools)


def call_tool(tool_invocation: dict) -> Runnable:
    """Function for dynamically constructing the end of the chain based on the model-selected tool."""
    tool_map = {tool.name: tool for tool in tools}
    tool = tool_map[tool_invocation["type"]]
    return RunnablePassthrough.assign(output=itemgetter("args") | tool)


import json


def human_approval(tool_invocations: list) -> Runnable:
    tool_strs = "\n\n".join(
        json.dumps(tool_call, indent=2) for tool_call in tool_invocations
    )
    msg = (
        f"Do you approve of the following tool invocations\n\n{tool_strs}\n\n"
        "Anything except 'Y'/'Yes' (case-insensitive) will be treated as a no."
    )
    resp = input(msg)
    if resp.lower() not in ("yes", "y"):
        raise ValueError(f"Tool invocations not approved:\n\n{tool_strs}")
    return tool_invocations


# .map() allows us to apply a function to a list of inputs.
call_tool_list = RunnableLambda(call_tool).map()
chain = model | JsonOutputToolsParser() | human_approval | call_tool_list
print(chain.invoke("how many emails did i get in the last 5 days?"))
print(chain.invoke("Send sally@gmail.com an email saying 'What's up homie'"))
