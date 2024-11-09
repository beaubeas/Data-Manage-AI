# Get the directory where the script is located
SCRIPT_DIR=$(dirname "$0")

# Construct the absolute paths for asshared and engine
ASHARED_DIR=$(realpath "$SCRIPT_DIR/../ashared")
ENGINE_DIR=$(realpath "$SCRIPT_DIR")

# Set PYTHONPATH to include asshared and engine directories
export PYTHONPATH="$ASHARED_DIR:$ENGINE_DIR:$PYTHONPATH"

export GIT_SHA=$(git rev-parse HEAD)
BASECMD="poetry run dotenv -f ../.env run"

if [ "$#" -ge 1 ]; then
    if [ "$1" == "python" ]; then
        $BASECMD ipython -i shell_start.py
    elif [ "$1" == "migrate" ]; then
        $BASECMD alembic upgrade head   
    elif [ "$1" == "makemigrations" ]; then
        $BASECMD alembic revision --autogenerate
    elif [ "$1" == "alembic" ]; then
        $BASECMD alembic $2
    elif [ "$1" == "history" ]; then
        $BASECMD alembic history
    elif [ "$1" == "docker" ]; then
        echo docker run -it -v ./storage:/code/storage --env-file ../.env -p 8080:8080 agents
        docker run -it -v ./storage:/code/storage --env-file ../.env -p 8080:8080 -p 8002:8002 agents
    elif [ "$1" == "triggersvc" ]; then
        echo docker run -it -v ./storage:/code/storage --env-file ~/envs/docker-agents.env -p 8080:8080 agents python -m supercog.engine.triggersvc
        docker run -it -v ./storage:/code/storage --env-file ~/envs/docker-agents.env -p 8080:8080 -p 8002:8002 agents python -m supercog.engine.triggersvc
    elif [ "$1" == "kill" ]; then
        ps -ef | grep "supercog\.engine" | awk '{print $2}' | xargs kill
    elif [ "$1" == "deploy" ]; then
        fly deploy --build-arg GIT_SHA=${GIT_SHA}
    elif [ "$1" == "tests" ]; then
        $BASECMD pytest
    elif [ "$1" == "runtest" ]; then
        $BASECMD pytest -s --disable-warnings $2
    elif [ "$1" == "enginemgr" ]; then
        $BASECMD python -m supercog.engine.enginemgr
    elif [ "$1" == "docker-runner" ]; then
        echo docker run -it -v ./storage:/code/storage -e RPC_PORT=9999 --env-file ~/envs/docker-agents.env -p 8080:8080 agents python -m supercog.engine.agent_runner
        docker run -it -v ./storage:/code/storage -e RPC_PORT=9999 --env-file ~/envs/docker-agents.env -p 8080:8080 agents python -m supercog.engine.agent_runner
    elif [ "$1" == "worker" ]; then
        $BASECMD python -m supercog.engine.enginemgr $2
    elif [ "$1" == "ragservice" ]; then
        $BASECMD python -m supercog.rag.ragservice
    else
        echo "Invalid command"
    fi
else
    $BASECMD python -m supercog.engine.main
fi


