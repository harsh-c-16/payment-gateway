[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { throw 'The prepared Python environment is missing.' }
# Compose scopes removal to this project's labelled containers/network. Never use -v or prune.
& $projectPython -c "from infra import prototype, postgres; print(prototype.compose('--profile', '*', 'down', '--remove-orphans', '--timeout', '40')); remaining=postgres.command(['docker','ps','--all','--quiet','--filter','label=com.docker.compose.project='+postgres.PROJECT]); raise SystemExit('Project containers remain after cleanup' if remaining else 0)"
if ($LASTEXITCODE -ne 0) { throw "Project container cleanup failed (exit $LASTEXITCODE)." }
Write-Host 'Project containers removed. Database/Kafka/lakehouse volumes, model files and images retained.' -ForegroundColor Green
