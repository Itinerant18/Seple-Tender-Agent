param (
    [Parameter(Mandatory=$true)][string]$Region,
    [Parameter(Mandatory=$true)][string]$AccountId,
    [Parameter(Mandatory=$true)][string]$ApiDomain
)

$ErrorActionPreference = "Stop"

# $ErrorActionPreference does not apply to native commands, so docker failures
# used to sail past and the script printed success on an image it never built.
function Invoke-Native {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Cmd)
    & $Cmd[0] @($Cmd[1..($Cmd.Length - 1)])
    if ($LASTEXITCODE -ne 0) { throw "FAILED (exit $LASTEXITCODE): $($Cmd -join ' ')" }
}

$Prefix = "seple-tender-prod"
$EcrBase = "${AccountId}.dkr.ecr.${Region}.amazonaws.com"

Write-Host "Logging into Amazon ECR..."
$Password = aws ecr get-login-password --region $Region
docker login --username AWS --password $Password $EcrBase

Write-Host "Building and pushing tender-api..."
Invoke-Native docker build -t "${Prefix}-api" -f Dockerfile.api .
Invoke-Native docker tag "${Prefix}-api:latest" "${EcrBase}/${Prefix}-api:latest"
Invoke-Native docker push "${EcrBase}/${Prefix}-api:latest"

Write-Host "Building and pushing hermes-agent..."
Invoke-Native docker build --build-arg VITE_TENDER_API_URL="https://${ApiDomain}" -t "${Prefix}-agent" -f Dockerfile .
Invoke-Native docker tag "${Prefix}-agent:latest" "${EcrBase}/${Prefix}-agent:latest"
Invoke-Native docker push "${EcrBase}/${Prefix}-agent:latest"

Write-Host "Building and pushing tender-scanner..."
Invoke-Native docker build -t "${Prefix}-scanner" -f Dockerfile.scanner .
Invoke-Native docker tag "${Prefix}-scanner:latest" "${EcrBase}/${Prefix}-scanner:latest"
Invoke-Native docker push "${EcrBase}/${Prefix}-scanner:latest"

Write-Host "Deployment images pushed successfully!"
Write-Host "ECS services should pick up the new images automatically if the tasks are restarted."
