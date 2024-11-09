# Supercog production is deployed to Fly.io

The "Ops Map" describes the various hosted services we are using:

https://docs.google.com/presentation/d/1meJTUzPU7OdvdOmAafMOVtMHqcDIJ60SYu7_6NUNCmA/edit#slide=id.g270bfb5aca3_0_0

- Use a Hosted Redis instance from Redislabs
- Use hosted Postgres from Digital Ocean (in NYC region)
- Deploy the Dasbboard via Docker containers:
    - We will bundle the Caddy and FastAPI processes into a single container and
      deploy themm together. The Caddy process will proxy to the FastAPI process. This
      should let us treat the "frontend" as a single addressable process which we can
      run multiple times for scale (using Redis to share sessions).
- Deploy Agents.sh as a separate container and process.
    - We can use Fly.io '.internal' addresses to address the Agents from the Dashboard
    - For Oauth we can proxy through Caddy, but using
        the separate `engine.supercog.ai` domain. Everything to this host gets
        proxied to the Agents service. The Agents service address should be configured in
        Caddy via a ENV var which references the Agents internal name. Hopefully the
        Fly.io internal network names will work for this.
- Deploy Triggersvc as a separate instance of the Engine container.

## Deploying the Agents service (using Redis for events)

- Had to configure a publicly addressable Redis server on Redis Labs

- Fly secrets:
    - ENV
    - DATABASE_URL
    - REDIS_URL
    - AWS keys, Slack keys, JIRA keys (don't think we actually use these)
    - S3 keys
    - SERP keys

### Docker for Agents

- Needed to copy monster/shared locally since docker won't access a parent dir
- Special setup to use Poetry to generate requirements.txt during build
- Run Uvicorn to respect HOST and PORT which are setup by Fly
to point to the internal vp6 hostname (this bind is important)
- Regular deploy via `fly deploy`
- We need a Fly volume for persisting files. Following this guide
    https://fly.io/docs/apps/volume-storage/
    I had to create volumes, then clone each machine:
    fly machine clone 9185927c227408 -r iad --attach-volume vol_42go819gne7yxz3v:/code/storage



## Deploying the Dashboard

The Dashboard builds a container with two processes: Caddy is the proxy/http server which
serves the front-end static files and it proxies all calls to the FastAPI backend process.

The backend process runs FastAPI and listens for proxied requests from Caddy.

So in practice we have 3 operable ports:

    Host env port (try to match the caddy port: 3000)
        -> Caddy bind port (3000)
            -> FastAPI port (8000)

We have to maintain all these values correctly:
    Caddy port, via the `PORT` **build* argument to the container. Needs to match
        whatever is in the build arg in the fly.toml file.
    FastAPI - leave to its default of 8000
    API_URL - address for Caddy to talk FastAPI, so fine to leave as "localhost:8080".


And deployed to Fly we sit behind THEIR proxy, so in fact we have that port also (443).

**Oauth flow**

To support our current Oauth flow the Agent service needs to be addressable at
least via the Caddy proxy. If we use Fly.io internal networking (based on Wireguard)
then it's possible that we could use Wireguard addressing even when running the
Agents service locally! We will have to experiement to see if we can get this to work.

One issue is when Caddy gets an oauth callback to "engine.supercog.ai" how will it
know which Agent service to proxy to? It may be enough to put the target Agent service
in the user's browser session and retrieve it from there.

# Front-door access

    User dashboard access
    https://app.supercog.ai
        -> through fly proxy, through Caddy, to Dashboard FastAPI

    OAUTH flow:
    https://engine.supercog.ai/run_oauth
        -> through fly proxy, through Caddy, proxied to the Engine service
    https://engine.supercog.ai/login/start_salesforce
    https://engine.supercog.ai/login/salesforce/authorized?
    https://engine.supercog.ai/login/finish_salesforce
        302 -> https://app.supercog.ai/sconnections
    
    SNS webhook:
        http://app.supercog.ai:8002/email_handler
        
        This is the Triggersvc. We will need to run this on a fly.io 
        private address, then have Caddy direct 8002 requests to that service.
        