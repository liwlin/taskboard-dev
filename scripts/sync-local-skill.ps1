# Sync the taskboard-dev release bundle to the local Claude Code skills
# directory. Syncs exactly the files staged by scripts/package.sh (the
# release manifest) - never mirrors the repo root, so development records,
# backlogs, and .taskboard runtime state stay out of the skill directory.

param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [string]$Destination = (Join-Path $env:USERPROFILE ".claude\skills\taskboard-dev"),
    [switch]$DryRun,
    [switch]$PruneStale
)

$ErrorActionPreference = "Stop"

$packageScript = Join-Path $RepoRoot "scripts\package.sh"
if (-not (Test-Path $packageScript)) {
    Write-Error "package.sh not found at $packageScript"
    exit 1
}

$manifest = @()
foreach ($line in Get-Content $packageScript -Encoding UTF8) {
    if ($line -match 'cp "\$ROOT_DIR/([^"]+)"') {
        $manifest += $Matches[1]
    }
}
if ($manifest.Count -eq 0) {
    Write-Error "No staged files found in package.sh manifest"
    exit 1
}

$missing = @($manifest | Where-Object { -not (Test-Path (Join-Path $RepoRoot ($_ -replace '/', '\'))) })
if ($missing.Count -gt 0) {
    Write-Error ("Manifest files missing from repo: " + ($missing -join ", "))
    exit 1
}

if ($DryRun) {
    Write-Output "Dry run - would sync $($manifest.Count) files to $Destination"
    $manifest | ForEach-Object { Write-Output "  $_" }
    if (-not $PruneStale) {
        Write-Output "Prune disabled - existing non-bundle files would be preserved"
    }
    exit 0
}

if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Force $Destination | Out-Null
}

foreach ($relative in $manifest) {
    $source = Join-Path $RepoRoot ($relative -replace '/', '\')
    $target = Join-Path $Destination ($relative -replace '/', '\')
    $targetDir = Split-Path -Parent $target
    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Force $targetDir | Out-Null
    }
    Copy-Item $source $target -Force
}

function Test-ProtectedLocalPath {
    param([string]$RelativePath)

    $parts = $RelativePath -split '[\\/]'
    foreach ($part in $parts) {
        if ($part.StartsWith(".")) {
            return $true
        }
    }
    return $false
}

$removedCount = 0
if ($PruneStale) {
    $manifestSet = @{}
    foreach ($relative in $manifest) {
        $manifestSet[($relative -replace '/', '\')] = $true
    }
    $stale = Get-ChildItem -LiteralPath $Destination -Recurse -File -Force | Where-Object {
        $relative = $_.FullName.Substring($Destination.Length).TrimStart('\')
        (-not $manifestSet.ContainsKey($relative)) -and (-not (Test-ProtectedLocalPath $relative))
    }
    foreach ($file in $stale) {
        Remove-Item -LiteralPath $file.FullName -Force -Confirm:$false
    }
    $removedCount = $stale.Count

    Get-ChildItem -LiteralPath $Destination -Recurse -Directory -Force |
        Sort-Object { $_.FullName.Length } -Descending |
        Where-Object {
            $relative = $_.FullName.Substring($Destination.Length).TrimStart('\')
            (-not (Test-ProtectedLocalPath $relative)) -and
                (-not (Get-ChildItem -LiteralPath $_.FullName -Force))
        } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -Confirm:$false }
}

Write-Output "Synced $($manifest.Count) bundle files to $Destination"
if ($PruneStale) {
    Write-Output "Removed $removedCount stale non-bundle files"
} else {
    Write-Output "Prune disabled - existing non-bundle files preserved"
}
