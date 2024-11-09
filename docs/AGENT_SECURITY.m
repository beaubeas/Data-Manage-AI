# Agent security

We use a JWT token to auth service calls between the Dashboard and the Agentsvc.

As system setup time, we generate an ECDSA key pair. The private key is configured
into the Dashboard as:

    DASH_PRIVATE_KEY=xxx

and the public key is configured into the Agent as:

    DASH_PUBLIC_KEY=xxx    

The Dashboard constructs a JWT token based on the logged in User.id and the Tenant Id.
It passes this token with every API request to the Agent.

The Agent decrypts the token using the public key and uses it to identify the User and Tenant,
and implicitly it verifies that the Dashboard is a valid client.
