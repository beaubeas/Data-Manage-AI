import re
from pydantic import BaseModel
from enum import Enum

class CommandType(str, Enum):
    RUN_AGENT_WITH_INPUT = 'RUN_AGENT_WITH_INPUT'
    ADD_MEMORIES = 'ADD_MEMORIES'
    REFLECT = "REFLECT"

class AgentCommand(BaseModel):
    action: CommandType

class RunAgentWithInput(AgentCommand):
    action: CommandType = CommandType.RUN_AGENT_WITH_INPUT
    input: str

class AddMemories(AgentCommand):
    action: CommandType = CommandType.ADD_MEMORIES
    memories: list[str]

class Reflect(AgentCommand):
    action: CommandType = CommandType.REFLECT

#### Define new command mappings here ####
COMMAND_MAPPINGS = {
    "/run": {
        "function": RunAgentWithInput,
        "pattern": r'^/run$\s?.*$',
    },
    "/add_memories": {
        "function": AddMemories,
        "pattern": r'^/add_memories (.+)$',
    },
    "/reflect": {
        "function": Reflect,
        "pattern": r'^/reflect\s?.*$',
    },
}

COMMANDS = list(COMMAND_MAPPINGS.keys())
COMMAND_PATTERNS = {cmd["pattern"]: cmd["function"] for cmd in COMMAND_MAPPINGS.values()}

def route_command(text) -> AgentCommand:
    if text is None or text.strip() == "":
        # Handle the case where text is None or an empty string
        return RunAgentWithInput(input="")
    
    command_patterns = COMMAND_PATTERNS

    for pattern, command_class in command_patterns.items():
        match = re.match(pattern, text)
        # Handle meta('/command') commands here
        if match:
            if command_class == AddMemories:
                memories = match.group(1)
                return command_class(memories=[memories])
            elif command_class == RunAgentWithInput:
                return command_class(input="")
            else:
                return command_class()

    return RunAgentWithInput(input=text)
