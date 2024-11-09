## Tools and Connections

Most tools will need _credentials_ to connect to some external system. An Assistant
will use a Tool, and the Tool will pull a Credential to operate.

    Agent ->
        Tool -> (including config options)
            Credential

We will support the notion of _shared_ and _private_ credentials. A Shared credential can be
used by anyone in the Tenant, while a private credential can only be used by the owner.

This allows us to distinguish "Tenant" credentials like a JIRA connection from a private
credential like a Gmail connection.

### Tools and credential fallback

When you configure your Agent, you will assign it a set of Tools. You can use any 
Tool which is available in the system. But when you attach the Tool to an Agent it
will try to _resolve_ a credential to use. If there are multiple matching private and
shared credentials, then the user will have to choose which one to use. Otherwise
the Tool will take whatever credential it can find, and it will remember this selection.

Now imagine that I have _shared_ an Agent between user A (the owner) and user B.
When user B _runs_ the agent it will need to resolve it's credentials. If all the
credentials are shared then it runs fine. But if the Agent references a tool which
references a _private_ credential then we will need to fallback and resolve a new credential.

This should allow user A to create an Agent which, for example, uses his private
GMail credential to send email. But then when **I** go run this Agent it will use
my Gmail credential instead.

## Oauth login support

Ah...fucking Oauth, the bane of my existence. Here is what we are doing circa Feb 27:

- Oauth flow is implemented by `Flask Dance` in a Flask App that is co-mounted inside
the `Engine` service. That thing has blueprints to drive (server side) Oauth flows.

- The Oauth client creds are expected to be set in the global config. So we expect
to use a sinuglar Salesforce client, Github client, etc.. with all users.

- The Engine provides a `/run_oauth` endpoint which takes a POST body to start off
the Oauth flow. The body indicates the various parameters needed by the Blueprint.
After the blueprint finishes authorization and token exchange, it calls up to
the FastAPI `main` module and passes the tokens and user info. The handler in 
main then creates a Credential record, tied to the user, to save the information.

- The Dashboard has support for `strategy_oauth` in the auth_config section of a ToolFactory.
If it sees this key then it builds an Oauth Login button and a form that includes all
the bits required for the Oauth flow, including the user_id of the requesting user (to 
save the Credential later). Because we need to preserve browser session in the Flask app, 
we actually POST the form from the **browser** via a `fetch` call that lives in
[custom.js](../dashboard/assets/custom.js). That fetch call POSTs to the Engine's
`run_oauth` path which returns a redirect to send the user through the Oauth flow
managed by the Flask app.

- Once the dance is complete then eventually the Flask app returns a redirect which
takes the user _back_ to the Dashboard.

- GOING TO PRODUCTION. In production Nginx fronts all the services, and serves SSL,
so we can't just expose the service port directly. Instead we use subdomains named
after the service, like `engine.llmonster.ai`, and have a Nginx rule to forward
requests to that host to the right backend port:

    if ($host = engine.llmonster.ai) {
        proxy_pass http://0.0.0.0:8001;
    }

In addition we have to regenerate our LetsEncrypt cert to cover both domains:

    certbot -nginx -d app.llmonster.ai -d engine.llmonster.ai

AND we have to configure CORS headers in Nginx (since the request will never reach
our server otherwise).

Finally we had to add another redirect URL to the Salesforce app:

    https://engine.llmonster.ai/login/salesforce/authorized


- Simple!

## Oauth clients

We could have 3 setups for managing oauth clients:

- "Global" Supercog clients that anyone can use. In this case any Supercog hosted user can
rely on our clients like the Google Auth client.
- "Per tenant" clients. In this model the Tenant could provide their own Oauth clients which 
we could use when doing oauth flows. We could still store these clients in our secrets store.

Currently we are relying on global clients we configure as ENV VARs.

But we could have a way for Tenant admins to configure Oauth clients for any oauth connectors
that they want their users to use. In this model the Tenant admin would create eg. a Salesforce
Oauth client, and add it to their Tenant settings. Then any user who created a Connection would
drive oauth through the Tenant's client. This would likely be a support nightmare, BUT could
be very very useful for Tenants that want to use/create dynamic connectors. 


## Implementing Tools

We use LangChain's support for "tools" as structured functions that can be
called by the LLM.

Here are some pertinent implementation notes for tools:

- Implement the "tool config" in the constructor. Pass the id, name, help, auth_config, logo.

- Use instance methods on your class to implement functions.

- Methods should be async and use async IO, although sync will work.

- Use `run_context` to get info about the currently running agent.

- User `self.log` to log messages to the Dashboard.

- You can also publish agent events from a function.

## File handling

Tools write read and write files from the local filesystem. To get an externally addressable URL
to a file, you can call:

    self.run_context.get_file_url(path)

## Dynamic Tools

To support our Slack integration, we have introduced a new mode for agents called "dynamic tools". 
In this mode, a new chat with your agent always resets the agent to have no tools except for the
"Auto Dynamic Tools" tool. With this tool your agent can automatically elect to use any available
tool while it is running. In this case the current tool list is kept stored on the Run object
itself. As the agent runs it can edit the list of tools on the run. If you start a new chat then
your agent resets to having no tools.

With this mode it doesn't make sense to add or edit the tools on the Agent itself, only on the
Run. So when you add a tool via the Dashboard, the meaning should only be "editing the list of tools
enabled for the current run". 

### Dynamic tool use cases

1. Start a new chat - tool list is empty
2. Ask the agent to add a tool and the tool appears as enabled
3. (Should we have a way to remove tools)
4. After adding some tools, you start a new chat and tool list resets
5. Go back to the other chat and the old list re-appears


