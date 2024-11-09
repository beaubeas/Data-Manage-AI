# Public agents

To date we have had a model where we assume a single "human" user in any chat conversation with 
the agent. But with the introduction of the Slack app, we want to enable the agent to work 
in _public_ Slack channels where multiple people could be in the same conversation (by responding
inside the same thread).

To support this, we need to make a few changes:

- When we send a prompt to the agent, we need to record the user which sent the prompt
  as the 'active' user on the RunLogs, which now may be different from the User who 
  created the Run. ✅ done

- We need to modify the input prompt to identify the "person speaking". This will automatically
have the effect of the agent knowing who it is talking to on any interaction. ✅ done

- Runs will now be shared across `scope=shared` agents, which means that any user can see 
all the Runs created for that agent (and can identify who created the Run.) ✅ done

- For full public use of Agents, we need to allow a non-auth'd Slack user to execute a public
agent. In this case we can just identify the user using their Slack user id in the JWT. ✅ done

- As an enhancement, we want to support "situation_context" as an attribute that a caller
can set when they prompt this agent. This is extra info that will be injected into the
agent prompt as "current situation":

    System: You are assisting the human in accomplishing their work. 
    You have a large variety of tools which you can 
    enable to accomplish specific tasks. You also have a wry sense of humour.
    When you are asked to do something, enable the appropriate tool to accomplish it, then proceed with the task.
    Human: 
    Human: 
    ======== Current Tools ========
    ==== Current Knowledge Indices ===
    ===========
    ==== Situation ===
    You are in a public Slack channel called "random".
    =========
