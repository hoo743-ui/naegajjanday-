# Pack what git does not carry (docs/66): env files, Claude memory, the local national DB.
# Run on the OLD PC from anywhere:   powershell -ExecutionPolicy Bypass -File scripts\migrate\export.ps1
# Output goes to your OneDrive (private, already synced to the new PC):  %OneDrive%\naegajjanday-migrate
#   -NoDb   skip the 1.2 GB database (the new PC can rebuild or copy it later)
param([switch]$NoDb)
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
if (-not $env:OneDrive) { throw "OneDrive is not set up on this PC - pass a folder by editing `$dest below." }
$dest = Join-Path $env:OneDrive "naegajjanday-migrate"
New-Item -ItemType Directory -Force "$dest\env", "$dest\memory", "$dest\db" | Out-Null

# 1. env files (they hold API keys: keep this folder private, never commit it)
$envs = @{ "apps\api\.env" = "api.env"; "apps\web\.env.local" = "web.env.local" }
foreach ($src in $envs.Keys) {
  $p = Join-Path $repo $src
  if (Test-Path $p) { Copy-Item $p (Join-Path "$dest\env" $envs[$src]) -Force; Write-Host "env    $src" }
  else { Write-Host "env    $src (missing, skipped)" }
}

# 2. Claude Code memory - stored per project path: every non-alphanumeric char of the path becomes '-'
$key = $repo -replace '[^A-Za-z0-9]', '-'
$mem = Join-Path $HOME ".claude\projects\$key\memory"
if (Test-Path $mem) {
  Copy-Item "$mem\*" "$dest\memory" -Recurse -Force
  Write-Host "memory $((Get-ChildItem $mem).Count) files from $key"
} else { Write-Host "memory not found at $mem (skipped)" }

# 3. local national DB + scorecard history
$data = Join-Path $env:LOCALAPPDATA "naegajjanday"
if (-not $NoDb) {
  $db = Join-Path $data "naegajjanday.db"
  if (Test-Path $db) {
    # a consistent copy even if the -wal file holds recent writes (python's sqlite backup API)
    $py = "import sqlite3; s=sqlite3.connect(r'$db'); d=sqlite3.connect(r'$dest\db\naegajjanday.db'); s.backup(d); d.close(); s.close()"
    python -c $py
    Write-Host "db     naegajjanday.db ($([int]((Get-Item "$dest\db\naegajjanday.db").Length / 1MB)) MB)"
  } else { Write-Host "db     not found at $db (skipped)" }
}
if (Test-Path "$data\eval") { Copy-Item "$data\eval" "$dest\db\eval" -Recurse -Force; Write-Host "db     eval history" }

$head = git -C $repo rev-parse --short HEAD
@"
naegajjanday migrate bundle
made:  $(Get-Date -Format s) on $env:COMPUTERNAME
repo:  $repo @ $head
WIP branches on GitHub: wip/r18-children, wip/16-mealtime
On the new PC: clone the repo OUTSIDE OneDrive, then run scripts\migrate\import.ps1 (docs/66).
This folder holds API keys - keep it private, delete it after importing.
"@ | Set-Content "$dest\README.txt" -Encoding UTF8

Write-Host "`nDone -> $dest"
Write-Host "Wait for OneDrive to finish uploading before using it on the new PC."
