source ~/envs/local.env
if [ -f "Dockerfile" ]; then
    DOCKERFILE="Dockerfile"
    CONTEXT=".."
elif [ -f "dashboard/Dockerfile" ]; then
    DOCKERFILE="dashboard/Dockerfile"
    CONTEXT="."
else
    echo "Dockerfile not found"
    exit 1
fi
echo $DATABASE_URL
docker build --build-arg GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID -f $DOCKERFILE -t dashboard:latest $CONTEXT
