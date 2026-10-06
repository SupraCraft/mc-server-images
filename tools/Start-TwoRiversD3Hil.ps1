param(
    [switch]$KeepRunning,
    [switch]$Publish
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Harness = Join-Path $RepoRoot 'tools\run_active4x_two_rivers_d3_hil.py'

$Python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = @('py', '-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = @('python')
} else {
    throw 'Python 3 is required for the D3 HIL harness.'
}

$Args = @($Harness)
if ($KeepRunning) {
    $Args += '--keep-running'
}
if ($Publish) {
    $Args += '--publish'
}

Push-Location $RepoRoot
try {
    if ($Python.Count -eq 2) {
        & $Python[0] $Python[1] @Args
    } else {
        & $Python[0] @Args
    }
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}
