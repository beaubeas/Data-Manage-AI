# Code Interpreter and Dynamic Tool building

Generally an agent should be able to use dymamic code execution to solve
immediate problems:

    User: Can you calculate the total value of the price column in the spreadsheet "transactions.xlsx"? 
    Agent:
        Sure.. let me generate some code to do that:
        execute_code(
            ```
                import pandas as pd
                data = pd.read_excel("transactions.xlsx)
                return data['price].sum()
            ```
        )
        ...
        The total value is: $2,229,402.

To implement this, we will enable the Agentsvc to manage a pool of Docker containers
running a Python interpreter session. These python sessions will be persistent
so that the agent can re-use results across multiple calls.

## Docker implementation

```
(main.py - singleton FastAPI server)
( >EngineMgr - singleton code to manage a set of running agents)
(   >AgentRunner - separate instance runs per running agent)
(     >ChatEngine - instance per AgentRunner instance, runs the LangChain agent)
```

Our core Agentsvc will itself run in a Docker container:

```
[ Agentsvc Container 
    -FastAPI app
        EngineMgr
]
    -- (xmlrpc) -->
        [ Container 1:
            AgentRunner
                ChatEngine ]
        [ Container 2:
            AgentRunner
                ChatEngine ]
        ...
```        

The EngineMgr will create Docker containers for each running Agent (as it does ChatEngines today).
We will move the EngineMgr "dispatch_input" function, which publishes agent events, down into
the per-agent container, and use XML-RPC to communicate to containers. Agents will be identified
by the Run ID and will have a dedicated port assigned for communication.

Each AgentRunner will have a persistent filesystem mounted which acts as the "agent filesystem".
This filesystem will look like this:

```
Physical disk:
    ./storage/
        <tenant_id>/           -> mounted as ./storage
            <user_id>           ->  CWD
```

This means that the "current directory" for the agent is the "user per tenant" directory. So
every agent run by a user sees the same filesystem. And from CWD they can see ".." which
is a folder shared across the entire tenant. 


### Code interpreter

We have support for a Code Interpreter as a tool, via `code.InteractiveInterpreter`. This will be the
basis for building dynamic tools.

The sandbox will support executing either Python code, or system commands. In the case of system commands
the AgentRunner will execute those within a subprocess in the container. This should allow, for example,
to do `pip install` to install new python packages which will be immediately available in the code
interpreter.

## Dynamic Tools

Once these pieces are in place, we will be ready to implement _Dynamic Tools_. This is the ability to work
interactively with your agent and create or update tools in real-time. Not only with the LLM be able
to run code, but we can create a protocol for dyanamically editing a new Tool (set of functions) which
will be persisted and usable by any agent.

For v1, we can save tools to file storage, and make that path available to the agents to load dynamic tools.

### Tool secrets

One thing to work out is how dynamic tools will get access to credentials for accessing a secured system,
in order that the agent can test functions that are written. At minimum we should have a _system space_
mechanism for the user to save named credentials.




