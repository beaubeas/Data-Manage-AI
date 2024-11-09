from typing import Optional
import re
from enum import StrEnum

from sqlmodel import (
    Session,
)

from supercog.dashboard.state_models import TemplateTool, TemplateState

class NodeTypes(StrEnum):
    HEADING1 = "h1"
    HEADING2 = "h2"
    CODE_BLOCK = "code"
    PARAGRAPH = "p"
    NUMBERED_ITEM = "ol"
#    STATE = "state"

class Node:
    tag: str
    content: str
    raw_content: str

    def __init__(self, tag: str, content: str, raw_content: str):
        self.tag = tag
        self.content = content
        self.raw_content = raw_content

    def __repr__(self):
        return f"<Node {self.tag}: {self.content}>"
        
NODE_REGEXP = {
    r"^#\s+(.*)" : NodeTypes.HEADING1,
    r"^##\s+(.*)": NodeTypes.HEADING2,
    r"^(\d+\.\s+.*)": NodeTypes.NUMBERED_ITEM,
#    r"^\s*\[(.*)\]": NodeTypes.STATE,
}

BLOCK_STARTS = {
    r"^```(.*)$": (NodeTypes.CODE_BLOCK, r"(.*)```"),
    r"^(.*)$": (NodeTypes.PARAGRAPH, r"^\s*$"),
}


def scan_markdown(text: str):
    def matches_special(line:  str) -> bool:
        return (
            any(re.match(pattern, line) for pattern in NODE_REGEXP.keys()) or
            re.match(list(BLOCK_STARTS.keys())[0], line) is not None
        )
   
    lines = text.splitlines()
    current = 0
    para = ""

   
    while current < len(lines):
        line = lines[current]
        for pattern, node_type in NODE_REGEXP.items():
            match = re.search(pattern, line)
            if match:
                yield Node(node_type, match.group(1).strip(), line)
                break
        else:
            block = ""
            for pattern, (node_type, end_pattern) in BLOCK_STARTS.items():
                match = re.search(pattern, line)
                if match:
                    block += match.group(1)
                    while current < len(lines):
                        current += 1
                        if current >= len(lines):
                            yield Node(node_type, block, block)
                            return
                        line = lines[current]
                        if match := re.match(end_pattern, line):
                            try:
                                block += match.group(1)
                            except IndexError:
                                pass
                            yield Node(node_type, block, block)
                            break
                        elif matches_special(line):
                            # implicitly close current block
                            yield Node(node_type, block, block)
                            current -= 1 # backup and return to main loop
                            break
                        else:
                            block += "\n" + line
                    break

        current += 1

def parse_markdown(text: str) -> list[Node]:
    return list(scan_markdown(text))

def lookup_factory_attribute_by_id(tool_factory_id: str, attribute: str, tool_factories: list[dict]):
    for tf in tool_factories:
        if tf["id"] == tool_factory_id:
            return tf.get(attribute)
    return None


def lookup_tool_factory_id_by_name(tool_name: str, tool_factories: list[dict]):
    for tf in tool_factories:
        if tf["system_name"].lower() == tool_name.lower():
            return tf["id"]
    return None

def import_agent_template_from_markdown(text: str, tool_factories: list[dict]) -> Optional[TemplateState]:
    # Note that tools are simply returned as the "tool string" provided
    # in the markdown, we should use this syntax:
    #   1. Tool name|Connection name|config_key=val,config_key=val2
    # where the tool name can be the display name or the factory_id. The Connection name and
    # config args should be supplied if the tool requires a credential.  
    nodes = parse_markdown(text)

    name = None
    model = ""
    instructions = []
    welcome = []
    image_url = ""
    tools = []
    max_chat_length = None

    node_idx = 0
    while node_idx < len(nodes):
        node = nodes[node_idx]
        if node.tag == NodeTypes.HEADING2:
            if match := re.match(r"name:\s+(.*)", node.content):
                name = match.group(1).strip()
            elif match := re.match(r"model:\s+(.*)", node.content):
                model = match.group(1).strip()
            elif match := re.match(r"image:\s+(.*)", node.content):
                image_url = match.group(1).strip()
            elif match := re.match(r"max_chat_length:\s+(.*)", node.content):
                max_chat_length = int(match.group(1).strip())
            elif match := re.match(r"system instructions", node.content):
                node_idx += 1
                while (
                    node_idx < len(nodes) and 
                    nodes[node_idx].tag in [NodeTypes.PARAGRAPH, NodeTypes.CODE_BLOCK, NodeTypes.NUMBERED_ITEM]
                ):
                    node = nodes[node_idx]
                    if node.tag == NodeTypes.CODE_BLOCK:
                        instructions.append(f"```\n{node.content.strip()}\n```")
                    else:
                        instructions.append(node.content.strip())
                    node_idx += 1
                node_idx -= 1
            elif match := re.match(r"welcome", node.content):
                node_idx += 1
                while node_idx < len(nodes) and nodes[node_idx].tag in [NodeTypes.PARAGRAPH]:
                    node = nodes[node_idx]
                    welcome.append(nodes[node_idx].content.strip() + "\n")
                    node_idx += 1
                node_idx -= 1
            elif match := re.match(r"\s*tools", node.content):
                node_idx += 1
                while node_idx < len(nodes) and nodes[node_idx].tag in [NodeTypes.NUMBERED_ITEM]:
                    node = nodes[node_idx]
                    # Remove \d+\. from the front of the line
                    content = re.sub(r"^\d+\.\s+", "", node.content)
                    tools_content = content.strip().split("|")
                    tool_name = tools_content[0]

                    tool_factory_id = lookup_tool_factory_id_by_name(tool_name, tool_factories)
                    if tool_factory_id is None:
                        tool_factory_id = tool_name
                        tool_name = lookup_factory_attribute_by_id(
                            tool_factory_id=tool_factory_id,
                            attribute="system_name",
                            tool_factories=tool_factories
                        )
                    if tool_factory_id is None:
                        # bad tool
                        print("Unknown tool: ", tool_name)

                    if len(tools_content) > 1:
                        tool_name = tools_content[1]

                    config={}
                    # Get the config from key value pairs like config_1=val_1,config_2=val_2
                    if len(tools_content) > 2:
                        config: dict = dict(item.split('=') for item in tools_content[2].split(','))

                    if tool_name and tool_factory_id:
                        tools.append(TemplateTool(
                            name=tool_name,
                            tool_factory_id=tool_factory_id,
                            logo_url=lookup_factory_attribute_by_id(
                                tool_factory_id=tool_factory_id,
                                attribute="logo_url",
                                tool_factories=tool_factories
                            ),
                            config=config,
                        ))
                    
                    node_idx += 1
                node_idx -= 1
        node_idx += 1

    if name is not None:
        return TemplateState(
            name=name,
            model=model,
            avatar_url=image_url,
            system_prompt="\n".join(instructions),
            welcome_message="\n".join(welcome),
            max_chat_length=max_chat_length,
            tools=tools
        )
    else:
        return None
