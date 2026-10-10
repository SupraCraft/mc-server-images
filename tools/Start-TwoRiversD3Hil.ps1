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
    # Observe, plan and fast-forward safely before HIL world creation.
    # Refuse divergent branches, dirty working trees, and destructive resets.
    $ExpectedBranch = 'feat/named-place-visual-qualification-v1'
    $CurrentBranch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $CurrentBranch -ne $ExpectedBranch) {
        throw "HIL requires the clean $ExpectedBranch branch."
    }
    $DirtyFiles = & git status --porcelain
    if ($LASTEXITCODE -ne 0 -or $DirtyFiles) {
        throw 'HIL will not overwrite local or untracked repository changes.'
    }
    & git fetch --quiet origin $ExpectedBranch
    if ($LASTEXITCODE -ne 0) { throw 'HIL source fetch failed.' }
    & git merge --ff-only "origin/$ExpectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'HIL branch has diverged; refusing a reset or rebase.' }
    $LocalHead = (& git rev-parse HEAD).Trim()
    $RemoteHead = (& git rev-parse "origin/$ExpectedBranch").Trim()
    if ($LASTEXITCODE -ne 0 -or $LocalHead -ne $RemoteHead) {
        throw 'HIL source verification failed.'
    }
    Write-Host "HIL source revision: $($LocalHead.Substring(0, 12))"
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
