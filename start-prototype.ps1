[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$privateBindings = Join-Path $PSScriptRoot 'artifacts/infra/prototype-local/.env'
if (!(Test-Path -LiteralPath $projectPython) -or !(Test-Path -LiteralPath $privateBindings)) {
    throw 'This launcher needs the prepared environment and retained bindings. See infra/PROTOTYPE.md for initial setup.'
}
function Invoke-ProjectPython {
    param([string[]]$Arguments)
    & $projectPython @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Prototype command failed (exit $LASTEXITCODE): python $($Arguments -join ' ')" }
}

function Test-DockerEngine {
    $probe = New-Object System.Diagnostics.ProcessStartInfo
    $probe.FileName = (Get-Command docker -ErrorAction Stop).Source
    $probe.Arguments = 'info --format {{.OSType}}'
    $probe.UseShellExecute = $false
    $probe.CreateNoWindow = $true
    $probe.RedirectStandardOutput = $true
    $probe.RedirectStandardError = $true
    $dockerProbe = [System.Diagnostics.Process]::Start($probe)
    try {
        if (!$dockerProbe.WaitForExit(5000)) { $dockerProbe.Kill(); return $false }
        return ($dockerProbe.ExitCode -eq 0 -and $dockerProbe.StandardOutput.ReadToEnd().Trim() -eq 'linux')
    } finally { $dockerProbe.Dispose() }
}

if (!(Test-DockerEngine)) {
    $desktopPath = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
    if (!(Test-Path -LiteralPath $desktopPath)) { throw 'Install Docker Desktop and enable its Linux engine first.' }
    Start-Process -FilePath $desktopPath -WindowStyle Hidden
    Write-Host 'Waiting for Docker Desktop...'
    $engineDeadline = [DateTime]::UtcNow.AddSeconds(120)
    $engineReady = $false
    while ([DateTime]::UtcNow -lt $engineDeadline) {
        Start-Sleep -Seconds 2
        if (Test-DockerEngine) { $engineReady = $true; break }
    }
    if (!$engineReady) { throw 'Docker Desktop did not become ready. Start its Linux engine and rerun this script.' }
}

$env:PROJECTCTL_ADAPTER_MODULE = 'infra.postgres'
Invoke-ProjectPython -Arguments @('-m','projectctl','env','up','--profile','postgres-local')
Get-Content -LiteralPath $privateBindings | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
Invoke-ProjectPython -Arguments @('-m','services.conversation.database')
Invoke-ProjectPython -Arguments @('-m','services.orders.m3_setup')
Invoke-ProjectPython -Arguments @('-m','pipelines.catalog.migrate','--variant','prototype')
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.prototype'
Invoke-ProjectPython -Arguments @('-m','projectctl','env','up','--profile','prototype-local')
Invoke-ProjectPython -Arguments @('-m','projectctl','env','verify','--profile','prototype-local')
$skuManifest = Join-Path $PSScriptRoot 'artifacts/prototype-setup/prototype-data/sku_manifest.json'
if (!(Test-Path -LiteralPath $skuManifest)) { throw 'The retained SKU manifest is missing; restore it before presenting. See infra/PROTOTYPE.md.' }
Invoke-ProjectPython -Arguments @('-m','projectctl','projection','wait','--namespace',$env:RUN_NAMESPACE,'--sku-manifest','artifacts/prototype-setup/prototype-data/sku_manifest.json','--timeout-seconds','600')
Invoke-ProjectPython -Arguments @('-m','projectctl','demo-check','--namespace',$env:RUN_NAMESPACE)
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'artifacts/infra/prototype-local/retrieval.json')) {
    Invoke-ProjectPython -Arguments @('-m','infra.retrieval','verify')
}
Write-Host 'Prototype ready: http://127.0.0.1:8001/' -ForegroundColor Green
Write-Host 'Use .\stop-prototype.ps1 after presenting. Data and model volumes are retained.'
