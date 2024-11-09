# Data Models

## Dashboard database

**Tenant**

This is the root of the user tree. There is one Tenant per "company" using the product.
Tenants are stored in `monster_dashboard`.

**User**

Represents each User in the system. and a User belongs to its Tenant.
Users are stored in `monster_dashboard`.


**TenantMember**

Join table to allow Users to be linked into multiple Tenants.

**Folder**

Container for agents, owner by a Tenant and User.

**Agent**

An Agent is an assistant configured with a name, LLM model, and a set of tools.
Each Agent belongs to a User, and thus a Tenant.
Agents are stored in `monster_dashboard`. Their spec will be posted to 
`Engine` service which will store its own copy.

The agent has a `scope` field with a value of either `private` or `shared`.
Shared agents are visible and runnable by everyone in the Tenant, while private are only
visible to the owner.

**Tool**

A tool is a configured "tool" that has been assigned to an agent. It references
its `ToolFactory` which indicates that type of Tool is is, and it typically will
have a reference to a Credential (an Engine model) which it needs to operate. 


## Agentsvc database

**ToolFactory**

This object is the factory for a Tool with a particular purpose. ToolFactories
are exported by the [Agent Engine](AGENTS.md) service and describe the available
tools within the system.

A ToolFactory has these properties:

`system_name` - The name of the system it connects to (like "JIRA")

`auth_config` - Describes how auth works for the system. Creating credentials
essentially amounts to configuring the `auth_properties` for a given ToolFactory.
The auth_config is a dictionary that maps different auth strategies to the
dict of parameters needed to configure. The Dashboard app will automatically
configure a form to complete the auth config.

Supported keys are:
`strategy_token`: Credentials are supplied by one or more static tokens
`strategy_oath`: Oauth flow is needed. Provide 'client_id', 'client_secret'
and so for as the options.

Examples:

system_name: JIRA
logo_url: ...
auth_config: {
    strategy_token: {
        "1. jira_token": "A personal access JIRA token"
        "2. jira_username": "The email for the personal access token"
        help: "Configure a personal access token at..."
    }
}

system_name: Slack
logo_url: ...
auth_config: {
    strategy_token: {
        slackbot_token: "The token for your Slack Bot"
        signing_secret: "The signing secret"
        help: "help markdown"
    }
}

system_name: Gmail
auth_config: {
    strategy_oauth: {
        token_creds: "The token creds JSON payload downloaded from Google",
        client_id: "The Google Auth client ID"
    }
}

**DocSource**

A DocSource is a specialization of `ToolFactory` that can provide a set of documents
to a DocIndex. It looks like a "tool" since it represents an authenticated connection
to some system (like Dropbox, Google Drive, S3 ...), and we may want these to provide
tools (like "search") for the Agent.

**Credential**

A credential is a named set of secrets needed to connect to some system. 

In the Dashboard we refer to _Connections_ but they are actually backed
by the Credential model in the Agentsvc. No "connection" object is stored
in the Dashboard db. The Dashboard only stores _Tools_ which link an
Agent to a ToolFactory and Credential.

Credentials are stored in the `monster_engine` database since they
are mostly used when running an Agent.

The credential has these properties:

- belongs to a User (who created it)
- `tool_factory_id` - The type of tool that can use this credential
- `scope` - The scope the credential can be used, `private` or `shared`.
- `name` - A user friendly name for the credential
- `secrets` - The secret references inside the credential. Specific to the system type.

Currently (before 'admin' roles) any user can create and autheticate a credential,
and they choose the credential's scope. Shared creds can be re-used by any other
User in the Tenant.

A `ToolFactory` defines an `auth_config` block with multiple auth strategies.
When you create a new Credential, the Dashboard will show a UI dynamically
from the definition in the auth_config. The values (secrets) set will be
stored as "{credential.id}:{name}" in the credentials service, and the same
list will be stored in Credentials.secrets. When you need the Credential
you call `resolve_secrets` and it will retrieve the secrets from the credential
store.

**DocIndex**

A DocIndex is a named, searchable index of documents (typically using a vector store). DocIndexes
are represented via their name to the user, as a defined "knowledge base" which can be accessed 
by an agent. DocIndexes are configured with zero or more "doc source" Connections that provide
their docs, and the user can also manually add documents into any index.

`name` - The name of the index
`scope` - whether the index is private or shared
`connections` - The list of doc source Connections attached to this index
`index_type` - The type of index (vector store, graph, etc...)


## To add

**OauthProvider**

We will add OauthProviders to the Agentsvc, so that ToolFactories can refer to the
OauthProviders that they support for auth.

