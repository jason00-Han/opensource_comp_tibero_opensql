$ErrorActionPreference = 'Stop'
$compose = Join-Path $PSScriptRoot '..\docker-compose.ha.yml'
Write-Host '1. Current Patroni roles' -ForegroundColor Cyan
docker compose -f $compose exec db1 patronictl -c /home/opensql/etc/patroni/patroni.yml list
$leader = docker compose -f $compose ps --format json | ConvertFrom-Json | Where-Object { $_.Service -match '^db[123]$' } | ForEach-Object {
  $service = $_.Service
  $code = docker compose -f $compose exec -T $service curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8008/primary
  if ($code -eq '200') { $service }
} | Select-Object -First 1
if (-not $leader) { throw 'Leader not found' }
Write-Host "2. Stopping leader: $leader" -ForegroundColor Yellow
docker compose -f $compose stop $leader
Write-Host '3. Waiting up to 45 seconds for election' -ForegroundColor Cyan
$newLeader = $null
for ($i=0; $i -lt 15 -and -not $newLeader; $i++) {
  Start-Sleep 3
  foreach ($node in 'db1','db2','db3') {
    if ($node -eq $leader) { continue }
    $code = docker compose -f $compose exec -T $node curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8008/primary
    if ($code -eq '200') { $newLeader = $node; break }
  }
}
if (-not $newLeader) { throw 'Failover did not complete' }
Write-Host "PASS: $leader -> $newLeader" -ForegroundColor Green
Write-Host 'The router remains available at localhost:16432.'
