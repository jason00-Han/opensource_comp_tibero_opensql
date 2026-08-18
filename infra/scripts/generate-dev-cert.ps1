$ErrorActionPreference = 'Stop'
$certDir = Join-Path $PSScriptRoot '..\nginx\certs'
New-Item -ItemType Directory -Force $certDir | Out-Null
docker run --rm -v "${certDir}:/certs" alpine/openssl req -x509 -nodes -newkey rsa:3072 -days 365 `
  -keyout /certs/privkey.pem -out /certs/fullchain.pem -subj '/CN=localhost' `
  -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
Write-Host "Development TLS certificate created in $certDir" -ForegroundColor Green
Write-Warning 'This self-signed certificate is for local development only. Use a trusted CA in production.'
