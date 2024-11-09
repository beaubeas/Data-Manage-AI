source ../.env
if [ -f "Dockerfile" ]; then
    DOCKERFILE="Dockerfile"
    CONTEXT=".."
elif [ -f "engine/Dockerfile" ]; then
    DOCKERFILE="engine/Dockerfile"
    CONTEXT="."
else
    echo "Dockerfile not found"
    exit 1
fi
docker build -f $DOCKERFILE -t agents:latest $CONTEXT
