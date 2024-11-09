# Agent UI

We would like agents to be able to create User Interfaces for the user to interact with.
Currently all UI is rendered inside the Dashboard. But this makes the agents less
capable to render their own UIs which would operate outside of the Dashboard.

## Web UI and event handlers

A user interface is generally a web page served from some server, plus some
set of backend handlers which implement actions for the UI.

Suppose we had this scenario: I want my JIRA agent to be able to render a
"New Issue" form. When the user submits the form then the agent should create a new
JIRA ticket.

In this pattern the UI basically takes the place of the prompt input, and submitting
the form is equivalent to sending a chat message.

Let's take another example. If the user asks my agent "Show me my JIRA tickets in a table",
then I want to render the result as an html table. But that table might need to support
paging for getting more records.

The problem is the "turn by turn" nature of the LLM completion doesn't fit well with
a UI which typically has a random access pattern where event handlers can be called in 
any order.

## Using Streamlit code gen

We could have a model where an agent could always generate a Streamlit app when it
wanted to render a UI. We could prompt the LLM that there are variables and functions
in the streamlit context that the generated page can use:

    run_context - standard variable
    # all tool functions are available
    # some set of server side functions (persistence, web+API requests)

Then the way an agent could "return" a UI is:

1. Generate the stream lit app
2. Send the app to the "app server", passing a handle to the run_context and tool functions
3. Return an event saying "Display the frame at this URL"

and our Dashboard can render the indicated frame. At this point that rendered web frame
and the Dashboard chat would both be able to send messages to the agent.

This would work for "inline" UIs when the agent is running, and maybe that's all the
support we need. 

### Example

So for my "Supercog Admin" agent, I could do this:

- Add a user prompt "Run the UI"
- Add the "Streamlit UI Gen" tool to my agent

- Give it these instructions:

- query for user counts by day for the last two weeks
- query for the most recent 10 users, including name and email
- query for the most recent 10 agent runs
- Now render the "admin_charts" streamlit app

... and now interactively, I would do this:

generate a streamlit app, that shows a chart of new users by day at the top,
then two columns, first with a table of recent users, and the second with
a table of recent agent runs.

The users should come by creating a variable "user_counts" which is the
count of users by day for the past week.

The latest users is a variable "new_users" which is a query of the most recent 10 users.
