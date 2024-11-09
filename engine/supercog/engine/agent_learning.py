from openai import OpenAI
import json
import re

from supercog.shared.logging import logger
from supercog.shared.models import RunOutput, RunLogBase
from supercog.shared.apubsub import (
    pubsub, 
    AgentLogEventTypes, 
    EventRegistry,
    AgentEvent,
    AgentInputEvent,
    AgentOutputEvent,
    AgentEndEvent,
    ToolEvent,
    ToolLogEvent,
    ToolEndEvent,
    AgentErrorEvent,
    ToolResultEvent,
    TokenUsageEvent,
    RequestVarsEvent,
    ChatModelEnd,
    AddMemoryEvent,
    EnableToolEvent,
    ChangeStateEvent,
)
from typing import List, Optional
from pydantic import BaseModel

from supercog.shared.services import config

class ReflectionResponse(BaseModel):
    facts:       List[str]
    analysis:    str
    token_usage: dict
    

OLD_REFLECTION_PROMPT = """
    We are running a system of AI Agents. Each Agent is configured with various tools that it
    can use to accomplish tasks. Your job is to reflect on a chat session between the agent 
    and the user and to design new "facts" that can help the agent operate more accurately
    in the future. When you generate a fact, format it like this example:
    FACT: the agent should never use the multi_tool_use function because it always throws an error.

    Please reflect on chat output recorded from an AI Agent. If you observe
    that the agent encountered an error and then resolved it, then please
    generate a FACT that can help the agent avoid that error in the future.
    ------------
"""

'''
## Step 5: Meta-Analysis
Look for higher-level patterns:
- Common error chains
- Successful problem-solving strategies
- User interaction patterns that lead to better outcomes
- Tool combinations that work well together


## Step 6: Context-Aware Documentation
For each fact generated, include:
1. The specific chat context where the pattern was observed
2. Any relevant user interactions that influenced the outcome
3. Alternative approaches that were attempted

## Additional Analysis Goals

Beyond error detection and resolution, analyze:

1. Efficiency Patterns
- Identify when the agent takes unnecessary steps
- Note opportunities for combining operations
- Recognize redundant tool usage

2. User Interaction Quality
- Note instances of clear vs. unclear agent responses
- Identify successful clarification strategies
- Document effective error communication patterns

3. Tool Selection Optimization
- Analyze tool selection decisions
- Document cases where alternative tools might have been more appropriate
- Identify patterns in successful tool combinations

4. Response Time Optimization
- Note operations that caused significant delays
- Identify opportunities for parallel operations
- Document successful optimization strategies
'''




# Agent Chat History Analysis Instructions

REFLECTION_PROMPT = """
You are tasked with performing a detailed analysis of chat sessions between AI agents and users. Your goal is to identify patterns, errors, and improvements to enhance agent performance. Follow these steps systematically:

## Step 1: Error Pattern Recognition
First, scan the chat history for the following patterns:
- Function call errors and their resolution attempts
- Tool usage patterns that led to failures
- Successful recoveries from previous errors
- Repeated attempts at similar actions with different parameters

## Step 2: Resolution Analysis
For each error identified:
1. Document the initial failed attempt:
   - Tool/function used
   - Parameters provided
   - Error message received
2. Document the successful resolution:
   - Changes in parameters
   - Changes in approach
   - New tools/methods used

## Step 3: Pattern Extraction
Analyze the differences between failed and successful attempts:
- Parameter formatting changes
- Alternative tool selections
- Modified input validation
- Changes in sequence of operations

## Step 4: Fact Generation
Generate facts in the following categories:

1. Error Prevention Facts
```
FACT: When [specific condition], the agent should [specific action] because [reasoning]
```

2. Tool Usage Facts
```
FACT: The [tool_name] tool works best when [condition] and should avoid [anti-pattern]
```

3. Recovery Strategy Facts
```
FACT: If [error_type] occurs, the agent should first try [recovery_step] before [alternative_approach]
```

4. Parameter Optimization Facts
```
FACT: For [function_name], parameters should be formatted as [format] to avoid [specific_error]
```
## Fact Generation Guidelines

When generating facts:
1. Be specific and actionable
2. Include clear conditions for application
3. Provide reasoning for the recommendation
4. Reference specific examples from the chat history
5. Consider edge cases and limitations
6. Include any relevant context or prerequisites

## Output Format

For each significant finding, use this structure:

OBSERVATION:
[Description of the observed pattern/issue]

ANALYSIS:
[Step-by-step breakdown of what occurred]

FACT:
[Actionable fact in the specified format]

SUPPORTING EVIDENCE:
[Relevant excerpts from the chat history]
"""
class AgentLearning:
    def __init__(self):
        pass

    def convert_run_logs_to_string(self, run_logs: [RunLogBase]):
        output = ""

        def format_result(k, v):
            if v.strip():  # Check if 'v' is not blank
                return f"{k}:\n{v}\n\n"
            else:
                return ""

        if run_logs[0].version == 3:
            return self.convert_version_3(run_logs)
        for log in run_logs:
            try:

                print(f"|||||||||||||||||Log role = {log.role} Content = {log.content}")
                if log.role == "user":
                    output += format_result(log.role, log.content)
                elif log.role == "agent":
                    if log.type == AgentLogEventTypes.OUTPUT:
                        output += format_result(log.role, log.content)
                    elif log.type == AgentLogEventTypes.TOOL:
                        tool_result = json.loads(log.content)
                        output += format_result(
                            log.role,
                            "USE TOOL: " + json.dumps({'function': tool_result['name'], 'args': tool_result['data']})
                        )
                    elif log.type == AgentLogEventTypes.SUBAGENT_OUTPUT:
                        output += format_result(
                            log.role,
                            "TOOL RESPONSE: " + log.content
                        )
            except Exception as e:
                print(e)
                pass
        return output

    def convert_version_3(self, run_logs: [RunLogBase]):

        output = ""
        for runlog in run_logs:
            agevent: AgentEvent = EventRegistry.get_event(runlog)

            match agevent:
                case AgentInputEvent():
                    if runlog.created_at:
                        output += f"Start Time: {runlog.created_at:%Y-%m-%d %H:%M:%S}"
                    output+= agevent.prompt
                case AgentOutputEvent():
                    output += agevent.str_result
                case ToolEvent():
                    output+= "Tool call: name: " + agevent.name + "data: " + json.dumps(agevent.tool_params)
                case ToolLogEvent():
                    if runlog.created_at:
                        output += f"Tool Result Time: {runlog.created_at:%Y-%m-%d %H:%M:%S}"
                    output += "Tool Output: "+ agevent.message
                case AgentErrorEvent():
                    if runlog.created_at:
                        output += f"Tool Result Time: {runlog.created_at:%Y-%m-%d %H:%M:%S}"
                    output += "Tool Error Output: "+ agevent.message
                case ToolResultEvent():
                    res = ""
                    if isinstance(agevent.output_object, str):
                        res = agevent.output_object
                    else:
                        res = json.dumps(agevent.output_object, indent=4)
                    output += "Tool Result: " + res

                case ToolEndEvent():
                    pass
                
                case TokenUsageEvent():
                    usage = agevent.usage_metadata
                    if 'input_tokens' in usage:
                        output += "Input Tokens: " + str(usage['input_tokens'])
                    if 'output_tokens' in usage:
                        output += "Ouput Tokens: " + str(usage['output_tokens'])

                case RequestVarsEvent():
                   output += "Requesting var: "+  agevent.var_names

                case AddMemoryEvent():
                    pass
                
                case EnableToolEvent():
                    output += "Adding tool: " + agevent.tool_factory_id

                case ChatModelEnd():
                    pass

                case AgentEndEvent():
                    pass

                case ChangeStateEvent():
                    pass
                case _:
                    # This case handles any unmatched event types
                    print("Runlog Recorded unknown event: ", agevent, " type: ", type(agevent))
            output+="\n"
        return output
                
    def reflect(self, run_logs: [RunLogBase]) -> tuple[list[str], dict]:
        logs_str = self.convert_run_logs_to_string(run_logs)

        print("---- Formatted runlogs -----")
        print(logs_str)
        print("---- Formatted runlogs end-----")
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": REFLECTION_PROMPT + "\n\n" + logs_str}
        ]
        client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={ "type": "text" },
        )
        print("Reflection result choices: ", response.choices)

        # Store token usage information
        self.last_token_usage = {
            'prompt_tokens':     response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens':      response.usage.total_tokens
        }

        analysis = response.choices[0].message.content
        logger.debug(analysis)
        
        facts = self.parse_facts(analysis)
        return ReflectionResponse(
            facts=facts,
            analysis=analysis,
            token_usage=self.last_token_usage
        )
    
    def parse_facts(self, result_string) -> list[str]:
        fact_pattern = r"FACT: (.*)"
        facts = re.findall(fact_pattern, result_string)
        return facts

    def get_last_token_usage(self) -> dict:
        """Returns the token usage from the last OpenAI API call."""
        return self.last_token_usage
