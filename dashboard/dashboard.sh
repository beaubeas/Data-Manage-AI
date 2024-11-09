#!/bin/bash

# When we run on localhost, we can just point to the backend
# running on port 8000. But in production behing Nginx with SSL
# then everythiing goes through the 443 port, and Ningx fowards
# the /_event path to our local port 8000. 
if [ "$ENV" = "prod" ]; then
  API_URL=https://app.supercog.ai
else
  ENV="dev"
  API_URL=http://localhost:8000
fi

# Get the directory where the script is located
SCRIPT_DIR=$(dirname "$0")

# Construct the absolute paths for asshared and engine
ASHARED_DIR=$(realpath "$SCRIPT_DIR/../ashared")
DASHBOARD_DIR=$(realpath "$SCRIPT_DIR")

# Set PYTHONPATH to include asshared and engine directories
export PYTHONPATH="$ASHARED_DIR:$DASHBOARD_DIR:$PYTHONPATH"
export GIT_SHA=$(git rev-parse HEAD)

BASECMD="poetry run dotenv -f ../.env run"

if [ "$#" -ge 1 ]; then
    if [ "$1" == "python" ]; then
        $BASECMD python -i shell_start.py
    elif [ "$1" == "migrate" ]; then
        $BASECMD reflex db migrate   
    elif [ "$1" == "makemigrations" ]; then
        $BASECMD reflex db makemigrations
    elif [ "$1" == "alembic" ]; then
        $BASECMD alembic $2
    elif [ "$1" == "debug" ]; then
        $BASECMD reflex run --loglevel=debug
    elif [ "$1" == "docker" ]; then
        echo docker run -it --env-file ~/envs/docker.env -p 3000:3000 dashboard
        docker run -it --env-file ~/envs/docker.env -p 3000:3000 dashboard
    elif [ "$1" == "test" ]; then
        $BASECMD pytest
    elif [ "$1" == "runtest" ]; then
        echo "Running tests"
        $BASECMD pytest -s --disable-warnings $2
    elif [ "$1" == "https" ]; then
        local-ssl-proxy --key ../localhost-key.pem --cert ../localhost.pem --source 3001 --target 3000 &
        API_URL=$API_URL $BASECMD reflex run --env $ENV --loglevel=info 
    else
        echo "Invalid command"
    fi
else
    API_URL=$API_URL $BASECMD reflex run --env $ENV --loglevel=info 
fi
