param([string]$ApiUrl='http://127.0.0.1:8000',[Parameter(Mandatory=$true)][string]$Token)
$ErrorActionPreference='Stop'
$headers=@{Authorization="Bearer $Token"}
$before=Invoke-RestMethod "$ApiUrl/health"
$temp=New-TemporaryFile
Set-Content -LiteralPath $temp -Value "failover pipeline marker $(New-Guid)" -Encoding utf8
try {
  $form=@{file=Get-Item -LiteralPath $temp}
  $upload=Invoke-RestMethod "$ApiUrl/v1/documents" -Method Post -Headers $headers -Form $form
  & "$PSScriptRoot/failover-demo.ps1"
  $deadline=(Get-Date).AddMinutes(3)
  do {
    Start-Sleep 3
    $job=Invoke-RestMethod "$ApiUrl/v1/jobs/$($upload.job_id)" -Headers $headers
  } while ($job.status -notin @('completed','failed') -and (Get-Date) -lt $deadline)
  if ($job.status -ne 'completed') { throw "Pipeline did not recover: $($job | ConvertTo-Json -Compress)" }
  $after=Invoke-RestMethod "$ApiUrl/health"
  Write-Host "PASS: pipeline job $($upload.job_id) completed across failover" -ForegroundColor Green
} finally { Remove-Item -LiteralPath $temp -Force }
