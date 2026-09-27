# Put the migrate bundle in place on the NEW PC (docs/66).
# 1) git clone https://github.com/hoo743-ui/naegajjanday-.git C:\dev\naegajjanday   (outside OneDrive)
# 2) cd C:\dev\naegajjanday
# 3) powershell -ExecutionPolicy Bypass -File scripts\migrate\import.ps1
#   -From <folder>   bundle folder (default %OneDrive%\naegajjanday-migrate)
#   -Force           overwrite existing env / memory / DB (old ones are kept as *.bak-<time>)
#   -SkipInstall     do not run uv sync / npm install / data-sync
param([string]$From = "", [switch]$Force, [switch]$SkipInstall)
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
if (-not $From) { $From = Join-Path $env:OneDrive "naegajjanday-migrate" }
if (-not (Test-Path $From)) { throw "Bundle not found: $From (run export.ps1 on the old PC, wait for OneDrive to sync)" }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

function Place($src, $dst) {
  if (-not (Test-Path $src)) { Write-Host "  - $(Split-Path $src -Leaf): not in bundle"; return }
  if ((Test-Path $dst) -and -not $Force) { Write-Host "  - $dst exists, kept (use -Force to replace)"; return }
  if (Test-Path $dst) { Rename-Item $dst "$dst.bak-$stamp" }
  New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
  Copy-Item $src $dst -Recurse -Force
  Write-Host "  + $dst"
}

Write-Host "[0] tools"
$missing = @()
foreach ($t in @(@("git", "Git.Git"), @("node", "OpenJS.NodeJS.LTS"), @("python", "Python.Python.3.13"), @("uv", "astral-sh.uv"))) {
  if (Get-Command $t[0] -ErrorAction SilentlyContinue) { Write-Host "  ok $($t[0])" }
  else { Write-Host "  MISSING $($t[0])  ->  winget install $($t[1])"; $missing += $t[0] }
}

Write-Host "[1] env files"
Place "$From\env\api.env" "$repo\apps\api\.env"
Place "$From\env\web.env.local" "$repo\apps\web\.env.local"
# the DB path is per machine: point DATABASE_URL at this PC's LocalAppData
$apiEnv = "$repo\apps\api\.env"
if (Test-Path $apiEnv) {
  $dbUrl = "sqlite+aiosqlite:///" + ($env:LOCALAPPDATA -replace '\\', '/') + "/naegajjanday/naegajjanday.db"
  $text = [IO.File]::ReadAllText($apiEnv)
  $new = [regex]::Replace($text, '(?m)^DATABASE_URL=sqlite\+aiosqlite:///.*naegajjanday\.db\s*$', "DATABASE_URL=$dbUrl")
  if ($new -ne $text) { [IO.File]::WriteAllText($apiEnv, $new); Write-Host "  DATABASE_URL -> $dbUrl" }
}

Write-Host "[2] Claude memory"
$key = $repo -replace '[^A-Za-z0-9]', '-'
$memDst = Join-Path $HOME ".claude\projects\$key\memory"
if (Test-Path "$From\memory") {
  New-Item -ItemType Directory -Force $memDst | Out-Null
  foreach ($f in Get-ChildItem "$From\memory") { Place $f.FullName (Join-Path $memDst $f.Name) }
  Write-Host "  project key: $key"
}

Write-Host "[3] local DB"
$data = Join-Path $env:LOCALAPPDATA "naegajjanday"
Place "$From\db\naegajjanday.db" "$data\naegajjanday.db"
Place "$From\db\eval" "$data\eval"

if (-not $SkipInstall -and $missing.Count -eq 0) {
  Write-Host "[4] install + data sync"
  Push-Location "$repo\apps\api"; uv sync; uv run python -m app.cli data-sync; Pop-Location
  Push-Location "$repo\apps\web"; npm install; Pop-Location
} elseif ($missing.Count) { Write-Host "[4] skipped: install the missing tools above, then run this again with -SkipInstall:`$false" }

Write-Host "`nDone. Next:"
Write-Host "  - open Claude Code in $repo and ask it to continue from the top of docs/PROGRESS.md"
Write-Host "  - WIP: git fetch; git switch wip/r18-children  (or wip/16-mealtime) - not reviewed, not on main"
Write-Host "  - delete the bundle folder when everything works (it holds API keys): $From"
