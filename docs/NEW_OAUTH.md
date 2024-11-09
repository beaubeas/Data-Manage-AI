# Existing Oauth support

Currently we support Oauth for Google and for Salesforce tools only.

This support is super, super hacky:

1. The Dashboard constructs a FORM for the "Connect to Salesforce" button, which actually
posts to the Agentsvc (via JS directly).

2. The Agentsvc gets the oauth dance request. It packs all the FORM data into URL parameters
and returns a redirect which just invokes oauth_flask.py.

3. oauth_flask.py actually runs the oauth flow, and when the auth code comes back it exchanges
it for the access token, then does a CALLBACK back up to main.py (our FastAPI app) with
the results of the token exchange.

4. main.py:oauth_login_callback gets called and it actually constructs a Credential record,
saves the tokens, and finally does a redirect back to the Dashboard.

5. The Dashboard gets the new Credential name in a page arg and it knows that the oauth flow is
done and saved.

This is all horrible:
 - Using crusty OauthFlask package
 - No extensibility other providers
 - Crazy redirect flow across multiple servers

-------------------
What do we really want? We want to be able to easily support the Oauth flow for LOTS of different
connected systems in a predictable way. We also want the ability to choose whether WE provide
the oauth client, or whether the customer provides their own oauth client. This could be either 
because we can't get a client (Google won't approve us) or the customer just wants to use their own
for security reasons.

Finally, we want to clean up this terrible code mess. As a stretch goal, we would like to expose
"configure and run an oauth flow" to our Agents so that someone could dynamically configure a new
Oauth flow, and run it, right from within the product. But again, this is a stretch goal.

------------------
# A possible design

## OauthProvider

We introduce the idea of an `OauthProvider`. This is a configuration spec for a system that supports
Oauth. This configures all the crazy little oauth bits:
- Name of the provider
- The authorize URL
- The token exchange URL
- How to get the refresh token
- The user profile URL
- Where to get the client ID and secret

I imagine that OauthProviders are basically YAML/JSON config which we stored in our database. Perhaps
they can be pre-loaded from source code. So a provider would look like this:

```yaml
spec_version: 1
spec_id: github
name: Github
client_id: config_customer_global["GITHUB_CLIENT_ID"]
client_secret: config_customer_global["GITHUB_CLIENT_SECRET"]
authorize:
	- url: https://github.com/oauth/authorize
	args:
		- scopes: config["GITHUB_SCOPES"]
		- arg2: ...
token: 
	- url: https://github.com/oauth/token
	- grant_type: web_flow
	- args:
		...
	- refresh_field: refresh_token
profile:
	- url: ...
```
Something like this. Those parts like `config_customer_global` says to "find this value
in the connection config, or then in the customer (tenant) config, or then in the global
Supercog config." 

## Oauth flow

So now, assuming we have defined `OauthProvider=Github` in the database, then we can implement
the oauth flow as follows. 

1. User requests to create a new Connection. We check auth_config and determine there is an
OauthProvider indicated
1. [Dashboard] Load OauthProvider, configure its variables
2. [Dashboard] If client is missing, explain to user how to go create it and then set it in the system 
(... user configures the client or we use Supercog built-in one...)
3. [Dashboard] 
   - creates "oauth instance" and saves it
   - Construct authorize link and show it to the user, where state=<oauth instance>

4. [user browser] follows authorize link, logs in to provider, redirects back to `redirect_uri`
5. [Dashboard] /oauth/<provider>?state=<instance> receives the auth callback.
    - loads the provider instance (the configured oauth provider)
    [..maybe we call to Agentsvc for below since it requires knowing the client Secret]
    - does the token exchange     - extracts the refresh token, calls the profile URL
    - saves the tokens to a Credential in the Agentsvc
    - creates a Connection object (dashboard side) referencing the Credential
    - confirms the oauth flow success to the user

Critically, we are running the flow from the _Dashboard_, and only calling the Agentsvc backend
to save the tokens (or maybe also exchange). This means the redirect_uri for the oauth client can refer 
to simply 'app.supercog.ai' and we only need to expose the dashboard to the internet.

### Dev process

We can start by implementing Salesforce, Google and Github oauth providers, and get the code working
for them. 

### Dealing with Salesforce

Salesforce is awful in that they really have *two* different oauth setups, "production" and "sandbox",
which use different URLs. I think the want we want to deal with this is:

SalesforceTool ->
  Connection ->
 	Credential ->
 		SalesforceProdOauthProvider | SalesforceSandboxOauthProvider

So the SaleforceTool config will look like this:

```
    auth_config = {
        "strategy_oauth": {
        	"providers": ["salesforce_oauth_prod", "salesforce_oauth_sandbox"]
        }
    }
```

This whole setup requires that the Dashboard be extended to support multiple ways to configure
a connection.

## Dynamic oauth providers

In the future we can support creating/editing Oauth providers within the Dashboard. This could
be as simple as a YAML text editor in the Dashboard. We could also create admin functions
so that the LLM could help define new OauthProviders by generating the YAML for us. Or maybe
we just create a system agent that has the spec and the instructions for the YAML, and we
just let the user copy-paste it.
