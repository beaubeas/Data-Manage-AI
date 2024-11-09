# The Agent execution Engine

In the beginning, agents we're so simple 😊. There was `main.py`, which implemented
a FastAPI api, and when you called it we created a `ChatEngine` object which constructed
our LangChain AgentExecutor.

So you started with `POST /run` which returned a Run ID.
Then you POSTed to `/runs/run_id/input` to send input to the agent. At this point
the `dispatch_input` method would start you agent, and as the agent published (slightly modified) LangChain events, we would re-publish events to Redis which went back to the Dashboard.

### Introducing files

When we introduced the agent filesystem things got more complicated. Now we had a filesystem
underneath each agent, and files were replicated to S3. When we added the _Datums_ page
then we needed a way to access all the data  (files, tables, dataframes) even if the
agent wasn't running. So we hacked logic to create the ChatEngine (and agent, and its tools)
on demand and reach through it to get agent datums.

Eventually main.py got super crazy, so I refactored lots of logic into the `EngineMgr`
class. This class now held the list of running agents (ChatEngine instances) and
`main.py` could focus on implementing API endpoints and delegating all the agent wrangling
to `EngineMgr`. This gave us this structure:
```
  main.py
    -> EngineMgr (single)
        -> ChatEngine|ChatEngine|ChatEngine
            >LCAgent+Tools|LCAgent+Tools|LCAgent+Tools
```

Cool! Except the original agent filesystem was a super hack and not secure in any way. Also we decided that we wanted a proper *code interpreter* tool. So this prompted refactoring the agents so that could run each one in separate Docker container.            

### Adding Docker and the Code Interpreter

Turns out the code interpreter is simple - Python has built-in support for a "python repl instance" and we use this for the code interpreter.

The bigger deal is running our agents in separate containers. To get to this, we added
the `AgentRunner` class as the dispatcher and manager of docker containers. This class
has a _direct_ mode, which uses local dispatch:
```
  main.py
    -> EngineMgr (single)
        -> AgentRunner|AgentRunner|AgentRunner
            -> ChatEngine|ChatEngine|ChatEngine
                >LCAgent+Tools|LCAgent+Tools|LCAgent+Tools
```
So really AgentRunner is just a facade on top of ChatEngine in this mode. But, if you enable
the AgentDockerRunner subclass, then each instance will run a Docker container for itself,
and methods you invoke on the AgentDockerRunner in EngineMgr will be proxied into the
container.
```
  main.py
    -> EngineMgr (single)
        -> AgentRunner(client)|AgentRunner(client)
            -> Container[AgentRunner(server)]|Container[AgentRunner(server)]
                -> ChatEngine|ChatEngine
                    >LCAgent+Tools|LCAgent+Tools|LCAgent+Tools
```


### New agent filesystem

Now that agents run in a container, we can implement their filesystem by simply mounting
their area in the supercog storage area (`SYSTEM_ROOT_PATH`) into the container. We mount
the per-Tenant folder so that agents can access shared tenant files, but the default director
is the per-user directory.


## Alembic migrations

Use this to generate new migrations:

    poetry run alembic revision --autogenerate

and to execute them:

    poetry run alembic upgrade head
    
## Refactor plan

-- Agent events

Agent events should be converted to proper Pydantic classes and serialized from there.

-- Tool function results

We should interrogate and "wrap" all tool function results for better representation
to the LLM:
    - Content that is too long should be returned like:
        The full results are 20,000 characters. The first 2000 characters are:
        ....
    - DataFrames should return a DataFrame preview

-- Tool function events

Tools need to be able to publish events:
    - log events
    - Mutation events like "tool function list changed"

We should create an "event publisher" object which is injected into all 
tools, and which they can call to publish events. This object should route
through EngineMgr which should centralize all actual Redis event publishing.

-- Agent context for Tools

We should replace ".meta" with an AgentContext object that is made
available to all tools. In fact this object should have the event publishing
methods, plus self description like agent_id and agent_name, etc...

This object should handle logging and whatnot, and we should remove any
"runtime" methods from ToolFactory.

-- File handling

File handling should all be implicit via normal file commands.

## Challenging event flows

To implement dynamic tools, we want a Tool which can acquire/edit its own functions.
But when those functions get edited, then Tool needs to publish an event so that:
- Its own agent gets reloaded to have the new tools (maybe all instances of the agent?)
- The Dashboard updates to show the new tools
