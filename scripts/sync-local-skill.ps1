# Sync the taskboard-dev release bundle to the local Claude Code skills
# directory. Syncs exactly the files staged by scripts/package.sh (the
# release manifest) - never mirrors the repo root, so development records,
# backlogs, and .taskboard runtime state stay out of the skill directory.

param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [string]$Destination = (Join-Path $env:USERPROFILE ".claude\skills\taskboard-dev"),
    [switch]$DryRun
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

$manifestSet = @{}
foreach ($relative in $manifest) {
    $manifestSet[($relative -replace '/', '\')] = $true
}
$stale = Get-ChildItem $Destination -Recurse -File | Where-Object {
    -not $manifestSet.ContainsKey($_.FullName.Substring($Destination.Length).TrimStart('\'))
}
foreach ($file in $stale) {
    Remove-Item $file.FullName -Force -Confirm:$false
}
Get-ChildItem $Destination -Recurse -Directory |
    Sort-Object { $_.FullName.Length } -Descending |
    Where-Object { -not (Get-ChildItem $_.FullName -Recurse -File) } |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -Confirm:$false }

Write-Output "Synced $($manifest.Count) bundle files to $Destination"
if ($stale.Count -gt 0) {
    Write-Output "Removed $($stale.Count) stale non-bundle files"
}
