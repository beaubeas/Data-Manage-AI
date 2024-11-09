#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "Error: This script requires exactly one argument."
    echo "Usage: $0 <dashboard|engine>"
    exit 1
fi

case "$1" in
    "dashboard")
        fly deploy --config ./dashboard/fly.toml --dockerfile dashboard/Dockerfile
        fly logs --app sc-dashboard
        ;;
    "engine")
        fly deploy --config ./engine/fly.toml --dockerfile engine/Dockerfile
        fly logs --app engine
        ;;
    *)
        echo "Error: Invalid argument. Please use 'dashboard' or 'engine'."
        exit 1
        ;;
esac
