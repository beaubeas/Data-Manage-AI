# Base data model

`Tenant` - This is an organization using our product. They have a name, current license plan,  
contact person, etc...  
>    `Team` - A team is a sub-group within a Tenant. Has a name and tenant_id.  
>        `User` - A user is user in the system. It belongs to one or more Teams.

We will use this data structure, but in the initial version of the product we won't 
distinguish Team from Tenant in the UI. There will just be Company (Tenant) and
each will contain a single Team that holds are Users.

## Agent

The core of our system is the `Agent` (which we call "Assistant" in the UI).
Each agent is created and owned by a User. It can have a scope of "user" or "team"
indicating its visibility.

    id
    name
    scope
    trigger
    ..other agent properties..

### Tools

An agent has a list of enabled `tools` which it can use during execution. Tools enable
the agent to take action, and they typically will interact with some other system. As such
they will generally need a credential (see the credentials service). to operate.

We will also define an interface so that other Agents can be used as tools. See
the `Agent Engine` below for more discussion of tools.

# Internal event bus

We have a PUBSUB internal bus for sending and receiving async events between services.
For now we can used a shared repo of Pydantic models to define all events. The
event classes will self-describe their topic channels.

# Credentials service

We need to store lots of secrets and credentials on behalf of our customers. We probably want
to use Hashicorp Vault or Amazon KMS or similar for security, but we will hide these details
behind our own privileged-access credential service.

This service simply stores and retrieves credentials on behalf of Tenants and Users. By
default a credential is linked to the User that created it, and can only be used by Agents
owned by that User. However the service should allow a credential to be stored for a Tenant
and thus usable by anyone's Agent.

## Credentials API

    POST /tenant/<tenant_id>/credentials
    user_id, meta {}, credentials {}
    <-- returns the credential_id

(future) "meta" holds aribitrary key,values which we can use to lookup a credential later. "credentials" is an opaque dictionary that should be stored encrypted.

If user_id is not null then it must be provided to retrieve the credential

    GET /tenant/<tenant_id>/credentials/<credential id>?user_id
    <-- returns a credential by ID. 
    
If the credential was created with a user_id then
it must be passed as an argument to retrieve the credential.


# Event service

This service listens for and dispatches events to trigger agents. It supports receiving
events from multiple systems on behalf of multiple tenants. Typical event sources include API polling, Webhooks, and Timer events.

"Triggers" represent triggers configured for an Agent. Triggers are fed to the Listener
as its configuration.

```
Trigger:
    system: [Gmail, Hubspot, Timer, ...]
    agent_id
    credential_id   -> ID of the credential we need for the Listener
    options: configuration for the trigger (like the Gmail inbox to listen to)
    active: bool - indicates if the trigger is active
```

The event service dispatches events via PUBSUB. An event looks like:
```
    trigger_id:
    tenant_id: (denorm)
    agent_id: (denorm)
    system: (denorm)
    timestamp:
    payload: {trigger specific}
```

The service runs "listeners" which listen for and dispatch (internally) events. There
is a Listener class per source system type. This class has a factory that generates
listeners from a trigger, and should attempt to re-use existing listeners if one
is compatible. So if we had 2 agents listening to Hubspot events, then we might get
one listener if the the two triggers were using the same credential.

## Event service API

```
POST /agent/<agent_id>/trigger - create a new trigger
PATCH /agent/<agent_id>/triggers/<trigger_id>
    - Update a trigger, including setting active=False
GET /triggers/<trigger_id> - return a trigger
DELETE /triggers/<trigger_id> - delete a trigger
```

# Docstore service

See [DOCSTORE](DOCSTORE.md).

# Agent Engine

See [AGENTS](AGENTS.md#agent-engine-service)

# Multi-service architecture

Each of our services will expose its API using FastAPI. API endpoints should be
annotated so they self-describe their schema. Each service will either be
stateless or else have its own dedicated database.

We will keep our core data models as Pydantic models in a shared repo. When we pass data 
between services we will pass the JSON serlialized versions of these models, and then
reconstruct them on the other side. If services need service-private data they should
subclass the base models and add private attributes there. So if a service needs data that is
not part of the serialized payload, then they have to make request to the source
service for it (for example, credential secrets will not be in the agent JSON. So
the Agent Engine will have to request the secrets from the credentials store.)

# Dashboard

The Reflex.dev app which serves our dashboard app.

# Software Layers
(lowest to highest)
```
shared_models/
    config_utils
    Agent
    Credential
    Trigger
    LLM
    Embedmodel
    Run
    Crawler
    Vectorstore
pubsub/ - Core pubsub utilites.
    events/
        pubsub event models
dbutil/
    - any utils for service storage
    - caching utils    
docstore/
credsvc/
eventsvc/
engine/
dashboard/
```

## (future) Model service

This service manages our available LLM and Embedding models. It exposes a catalog
of available models, but a Tenant needs to configure their own models before they
can be used by agents. Generally models are either "internal" or "hosted". Internal
models are runs that we are running ourselves, vs. hosted models that run elsewhere.
In the case of internal models our service will expose an API to call them, so
from the perspective of the Agent Engine all models are accessed through API calls.



