## Refactor list

### Redis PubSub

We should refactor the communication between Agents and Dashboard to work over a single
websocket instead of HTTP requests and Redis Pubsub events back. At least this should be
a config option because it means that user's could run the Agents service without
exposing any public ports. Maybe we would keep Redis around for local use, but not try
to use it between Dashboard and Agents.

### Agent security

The Dashboard should encrypt all its requests using its private key, and it should
export its public key to the Agents so they can verify Dashboard requests.

In theory we don't really need to encrypt agent events back to the Dashboard as
long as we never persist those events (they are only persisted by the Agent service
itself.)
