# LLMonster

This product allows anyone to build LLM-enabled applications that connect to your
corporate information systems. Writing a new _Assistant_ is as simple as 
selecting a set of [tools](docs/TOOLS.md) and writing an instruction to the
Agent in plain English.

The premise is that LLMs (especially GPT4 at the moment) can be really, really
smart but they mostly live inside a sandbox. By connecting them to your corporate
systems you can easily build smart automation in your work.

Examples:

**Email assistants** - which intelligently process email for you. Auto-respond, or
create internal docs/tickets from messages, or look for Google Meet recordings and
generate annotated summaries.

**System integrations** - trigger on a new JIRA ticket and post a message to Slack,
with abitrary rules.

**Data access** - lookup records in a database or a SaaS system (JIRA, Google Docs, ...)
and use the answer as part of your Assistant's logic. Want to ping a "CEO notify"
Slack channel if there's a support ticket from a high value customer (by examining
their spend in the database)?

**Chatbots** - Easily build a chatbot on top of internal knowledge, web browsing,
pre-trained data in the LLM, or any combination.


## Setup

Most of the code is a Reflex.dev app.

1. Make sure you have python 3.11 installed and active (use "poetry env use python@3.11")
2. Run `poetry install`
3. `poetry shell`
4. Set `OPENAI_API_KEY` in your environment
5. Run `reflex init` (This creates the runnable app in `.web`)
6. `reflex run` (make sure the poetry env is active)

Whenever packages change you will need to run `poetry install` again.

You need more components for various tools:

Database query - You need Postgres running locally and set the DB connection string in Settings.
Email trigger - You will  need Redis (see [redis.sh](redis.sh) ).

When you are running, some LLM logging will go to the console. But the full LLM context and history will get written to `output.log`.

## How it works

All the Reflex code is in:

    streetlamp/
        assets/
        components/
        pages/
        templates/
        state_models.py
        state.py
        streetlamp.py

Currently it uses a janky "key value" store to store everything in a SQLite database. We will move to
Postgres and a real ORM soon.

All the "LLM-based app" stuff lives under:

    streetlamp/engine

In here the ChatEngine class runs a LangChain Agent chain which sends the trigger
input to the chosen LLM and returns the results. This class also maps
any Tools selected for use by the LLM into the chain.

LangChain "Agent" provides the basic agent loop which executes function calls and
returns the results to the LLM. This one seems to work about as well as Open AI Assistants
and its not a black box like that is.

## The apps listing page.

![Apps Page](../docs/apps_page.png)

## The app editor page with built-in chat.

![Editor Page](../docs/app_editor.png)


## OAuth flow

Other than Google auth for login, which ues a React component, we mostly do
the OAuth dance server side.

A button in the Dashboard links to a login path served by the `engine` service:

<Login with Salesforce> -> https://app.llmonster.ai:8001/login/salesforce

The engine service, inside `oauth_flask` handles the `/login/salesforce`
request, generates the Salesforce Oauth URL and redirects the browser there.
After logging in the return comes BACK to the engine service at 
`/login/salesforce/authorized`. That calls back up into the FastAPI app
which saves the user tokens and details to a new Credential for the User
and then redirects the browser back to the Dashboard.

So:

    Dashboard 
        -> (login with Salesforce)
          Engine 
            -> (redirect to Salesforce login)
              Salesforce
                <- login and redirect back to Engine
          Engine (save the users tokens in a Credential)
            <- redirect back to the Dashboard
    Dashboard
      show evidence of the new Credential

# Future

Check out the [Architecture](docs/ARCHITECTURE.md) docs for a longer description of the project plans.

# TODO


1.1 [to test] Enable Slack chat interface trigger
1.2 Publish Slack Bot
1. Add "default" Agents when we create a new Tenant
1. Create "Running Agents" screen which lets you monitor all background agents
1. Allow users to use '#' comments in their Assistant prompts, and filter them out 


1. [done] Refactor all the tool functions into tool_factory.py
1.1 [done] Enable web browsing tool with no credential
1.2 [done] Fix Redis channels so you can run agents separately (don't use 'logs')
1. [done] Create proper Login page, require login
2. [WIP] Fix Google login to use longer session time
    - add Google scopes to enable email (in and out)
3. [done] Filter "All assistants" by tenant_id
4. [done] Separate "Shared" vs. "Private" assistants
5. [done] Add "test prompt" as a property of an Agent
5.1 [done] Add a "New Agent" page with descriptions of types of Agents
you can build
6. [done] Implement Dall*e generated Agent images
7. [done] Fix render bug on "Run App" page with chart start obscured


## Beta experience

- Login with your Google Domain email. Creates a shared Tenant
  for that domain.
- First user configures Connections, especially configuring Slack Bot
  (so tools are Slack, web browser, database. Maybe they have JIRA also?)
- Should pre-populate a set of "default" Agents so people have
some examples to see and run.
- Then it's down to some excited initial user who wants to try things
out or has Tools they need.


