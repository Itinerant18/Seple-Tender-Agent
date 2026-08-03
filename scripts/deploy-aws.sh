#!/bin/bash
set -e

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <aws-region> <aws-account-id> <api-domain>"
    echo "Example: $0 ap-southeast-1 123456789012 api.yourdomain.com"
    exit 1
fi

REGION=$1
ACCOUNT_ID=$2
API_DOMAIN=$3
PREFIX="seple-tender-prod"
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "Logging into Amazon ECR..."
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_BASE

echo "Building and pushing tender-api..."
docker build -t ${PREFIX}-api -f Dockerfile.api .
docker tag ${PREFIX}-api:latest ${ECR_BASE}/${PREFIX}-api:latest
docker push ${ECR_BASE}/${PREFIX}-api:latest

echo "Building and pushing hermes-agent..."
docker build --build-arg VITE_TENDER_API_URL=http://${API_DOMAIN} -t ${PREFIX}-agent -f Dockerfile .
docker tag ${PREFIX}-agent:latest ${ECR_BASE}/${PREFIX}-agent:latest
docker push ${ECR_BASE}/${PREFIX}-agent:latest

echo "Building and pushing tender-scanner..."
docker build -t ${PREFIX}-scanner -f Dockerfile.scanner .
docker tag ${PREFIX}-scanner:latest ${ECR_BASE}/${PREFIX}-scanner:latest
docker push ${ECR_BASE}/${PREFIX}-scanner:latest

echo "Deployment images pushed successfully!"
echo "ECS services should pick up the new images automatically if the tasks are restarted."
