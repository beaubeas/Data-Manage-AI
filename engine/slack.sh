# Get the directory where the script is located
SCRIPT_DIR=$(dirname "$0")

# Construct the absolute paths for asshared and engine
ASHARED_DIR=$(realpath "$SCRIPT_DIR/../ashared")
ENGINE_DIR=$(realpath "$SCRIPT_DIR")

# Set PYTHONPATH to include asshared and engine directories
export PYTHONPATH="$ASHARED_DIR:$ENGINE_DIR:$PYTHONPATH"

poetry run dotenv -f ~/envs/local.env run python -m supercog.engine.slack.app
