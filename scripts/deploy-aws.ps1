param (
    [Parameter(Mandatory=$true)][string]$Region,
    [Parameter(Mandatory=$true)][string]$AccountId,
    [Parameter(Mandatory=$true)][string]$ApiDomain
)

$ErrorActionPreference = "Stop"

$Prefix = "seple-tender-prod"
$EcrBase = "${AccountId}.dkr.ecr.${Region}.amazonaws.com"

Write-Host "Logging into Amazon ECR..."
$Password = aws ecr get-login-password --region $Region
docker login --username AWS --password $Password $EcrBase

Write-Host "Building and pushing tender-api..."
docker build -t "${Prefix}-api" -f Dockerfile.api .
docker tag "${Prefix}-api:latest" "${EcrBase}/${Prefix}-api:latest"
docker push "${EcrBase}/${Prefix}-api:latest"

Write-Host "Building and pushing hermes-agent..."
docker build --build-arg VITE_TENDER_API_URL="https://${ApiDomain}" -t "${Prefix}-agent" -f Dockerfile .
docker tag "${Prefix}-agent:latest" "${EcrBase}/${Prefix}-agent:latest"
docker push "${EcrBase}/${Prefix}-agent:latest"

Write-Host "Building and pushing tender-scanner..."
docker build -t "${Prefix}-scanner" -f Dockerfile.scanner .
docker tag "${Prefix}-scanner:latest" "${EcrBase}/${Prefix}-scanner:latest"
docker push "${EcrBase}/${Prefix}-scanner:latest"

Write-Host "Deployment images pushed successfully!"
Write-Host "ECS services should pick up the new images automatically if the tasks are restarted."
