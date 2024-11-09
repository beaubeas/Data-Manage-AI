# Dashboard

The LLMonster dashboard application, using _Reflex.dev_.

## Running tests

    psql> CREATE DATABASE dashboard_test
    DATABASE_NAME="dashboard_test" reflex db makemigrations
    DATABASE_NAME="dashboard_test" reflex db migrate

    poetry run pytest
    
## TODO

The next step is to refactor the code to:

- Rebuild the Settings page to show Private and Shared Credentials,
and let you add or edit both.
- Refactor the Agent Editor so that it creates Tool models that
refer to a ToolFactory and resolve a Credential for use.
- Refactor the engine to resolve credentials for tool use.
- Add support for Private vs. Shared Agents, with credential resolving
logic for each.
- Remove "App Tools" for now.
