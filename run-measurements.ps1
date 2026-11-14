[CmdletBinding()]
param([switch]$Smoke, [switch]$Quick, [double]$Cpus = 1, [int]$MemoryMiB = 2048,
      [int]$TimeoutMinutes = 120)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$measurementPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$measurementArgs = @('-m','benchmarks.windows.measure','--cpus',"$Cpus",'--memory-mib',"$MemoryMiB")
$measurementArgs += @('--timeout-minutes',"$TimeoutMinutes")
if ($Smoke) { $measurementArgs += '--smoke' }
if ($Quick) { $measurementArgs += '--quick' }
& $measurementPython @measurementArgs
if ($LASTEXITCODE -ne 0) { throw 'Measurement failed. Inspect artifacts/windows; partial evidence is retained.' }
Write-Host 'Comparisons and raw evidence saved under artifacts/windows. Disposable PostgreSQL removed.'
