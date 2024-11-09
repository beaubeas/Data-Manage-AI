## Building Agents

On the **[Connections](/sconnections)** page you can configure connections to any systems
that your agent will need to access:

- Email tool
- Slack tool
- JIRA tool
- Database tool
...

Now follow these steps to create a **[new Agent](/create_app/recent/)**:

1. Give your agent a descriptive name and description
2. Decide how you want to trigger your agent. By default your agent
is an interactive chat bot, but you can trigger the agent automatically
based on events like the arrival of an email message.
3. Click _Add Tool_ and select the tools that you want your 
agent to be able to use. 
4. You can change the LLM model used by your agent in the _Settings_ panel.
5. Now edit the instructions to your agent. These instructions can
be anything, but the general flow will include:

- What to look for in the input data. 
- Add any rules about when the agent should or should not take some action
- Instruct the agent how to respond. By default the agent will
"answer" the request in text, but many agents will also use some tool
to accomplish an action, like creating a JIRA ticket.

Here are some simple examples:

    _
    You are a helpful agent. If you receive an email from boss@example.com, and  
    the tone of the email seems urgent or angry, then send me a Slack message with  
    the content "Alert! " plus the subject of the email. Otherwise do nothing.

----
    _
    The user will enter the details of an email message. When you receive it and ONLY
    if the sender is present in the User table then generate a JIRA ticket in the "AB"
    project, and post the email subject line with the JIRA ticket link to the Slack 
    "general" channel. 
----
    _
    Use the subject of the email as the ticket summary, and use the body of the email, 
    plus the sender, plus a note '(Made by LLMonster)') as the ticket description. 
    Don't ask any questions, just follow this instruction.

