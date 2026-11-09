$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$tlsDirectory = Join-Path $projectRoot "tls"
$certificatePath = Join-Path $tlsDirectory "dev.crt"
$keyPath = Join-Path $tlsDirectory "dev.key"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required to generate local certificates. Install Docker Desktop, then rerun."
}

New-Item -ItemType Directory -Force -Path $tlsDirectory | Out-Null
& docker run --rm -v "${tlsDirectory}:/certs" alpine/openssl req -x509 -nodes -days 365 `
    -newkey rsa:2048 -keyout /certs/dev.key -out /certs/dev.crt `
    -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

if ($LASTEXITCODE -ne 0) {
    throw "Docker could not generate the local development certificate."
}

Write-Host "Created local self-signed HTTPS certificate in $tlsDirectory"
Write-Host "Your browser will show a certificate warning until this cert is trusted."
Write-Host "Do not use this self-signed certificate for production."
