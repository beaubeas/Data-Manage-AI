import pytest

from supercog.engine.chatengine import ChatEngine
from supercog.shared.models import AgentCore

@pytest.fixture
def chatengine():
    return ChatEngine()

@pytest.fixture
def agent_instructions() -> str:
    return """
[[start]]
``` 
Hi! This is the start welcome message.
```

Ask the user for their name and their job function. 
2. Step 2

[[intro]]
```
I am capable of helping with a variety of tasks.
```

If the user asks for a demonstration, then transition to the "demo" state. Otherwise
transition to the "default" state.

[[demo]]
``` 
    Great! Let's walk through a demo.
```
The user has requested a demonstration on how to to design a simple "weather info" agent. 
Follow these steps for the demo:
1. Suggest the user ask for the weather prediction in their current location
2. Now, suggest that the user request to enable the Weather tool
3. Now suggest the user ask about the weather again


[[default]]
```
Welcome! How can I help you today?
```

You are an expert systems integration consultant. You have deep expertise
"""

def test_state_parsing(chatengine, agent_instructions):
    agent = AgentCore(id="a1", name="foo", system_prompt=agent_instructions)

    all = agent.get_agent_states()
    assert all == ["start", "intro", "demo", "default"]

    prompt = chatengine.get_active_prompt(agent_instructions, "intro")
    print(prompt)
    assert "capable" not in prompt
    assert "If the user asks" in prompt

    prompt = chatengine.get_active_prompt(agent_instructions, "demo")
    print(prompt)
    assert "Great" not in prompt
    assert "3. Now suggest the user" in prompt

    prompt = chatengine.get_active_prompt(agent_instructions, "unknown")
    print(prompt)
    assert "You are an expert systems integration consultant" in prompt

    map = agent.get_state_welcome_message_map()
    assert "start" in map
    assert "intro" in map
    assert "demo" in map
    assert "default" in map

def test_with_no_states(chatengine):
    reg_prompt = """
You are a helpful assisant. Follow these steps:
1. Do the first thing
2. Do the second thing
"""

    prompt = chatengine.get_active_prompt(reg_prompt, "start")
    assert "Do the first" in prompt
    assert "Do the second" in prompt
