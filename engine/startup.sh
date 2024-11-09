#!/bin/bash
set -e

# Run any startup tasks here
echo "Running startup tasks..."

export PYTHONPATH=$PYTHONPATH:/code

# Finally, execute the main command
exec "$@"