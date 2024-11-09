#!/bin/bash

# Check if correct number of arguments are provided
if [ "$#" -ne 1 ]; then
    echo "Error: This script requires exactly one argument."
    echo "Usage: $0 <dashboard|engine>"
    exit 1
fi

# Set variables
REPO_NAME="$1"
ORG_NAME="supercogai"
DATETIME_TAG=$(date +"%Y%m%d_%H%M%S")

# Change to the directory where the script is located
cd "$(dirname "$0")"

# Build the Docker image
echo "Building Docker image from ./$REPO_NAME..."
docker build -f $REPO_NAME/Dockerfile -t $ORG_NAME/$REPO_NAME:$DATETIME_TAG -t $ORG_NAME/$REPO_NAME:latest .

# Check if the build was successful
if [ $? -eq 0 ]; then
    echo "Docker image built successfully"
else
    echo "Docker image build failed"
    exit 1
fi

# Push the image to Docker Hub
echo "Pushing image to Docker Hub..."
docker push $ORG_NAME/$REPO_NAME:$DATETIME_TAG
docker push $ORG_NAME/$REPO_NAME:latest

# Check if the push was successful
if [ $? -eq 0 ]; then
    echo "Image successfully pushed to Docker Hub"
    echo "Image: $ORG_NAME/$REPO_NAME:$DATETIME_TAG"
else
    echo "Failed to push image to Docker Hub"
    exit 1
fi
