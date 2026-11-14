param(
  [string]$Database = (Join-Path $PSScriptRoot '..\.recovery\workspace-acceptance\workspaces.sqlite3')
)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $Repo 'venv\Scripts\python.exe'
$Database = [System.IO.Path]::GetFullPath($Database)
$AllowedRoot = [System.IO.Path]::GetFullPath((Join-Path $Repo '.recovery\workspace-acceptance')).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $Database.StartsWith($AllowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw 'Workspace acceptance DB must stay under .recovery\workspace-acceptance; application databases are not valid targets.'
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Project virtualenv Python not found: $Python" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Database) | Out-Null

$secure = Read-Host 'Enter a private synthetic-account password (12+ characters)' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $env:SACCO_ACCEPTANCE_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
$env:SACCO_ACCEPTANCE_DB = $Database
$env:DJANGO_SETTINGS_MODULE = 'sacco.acceptance_settings'

Push-Location $Repo
try {
  & $Python manage.py check --settings=sacco.acceptance_settings
  if ($LASTEXITCODE -ne 0) { throw 'Django system checks failed.' }
  & $Python manage.py migrate --settings=sacco.acceptance_settings --noinput
  if ($LASTEXITCODE -ne 0) { throw 'Workspace acceptance migrations failed.' }
  & $Python manage.py seed_workspace_acceptance --settings=sacco.acceptance_settings
  if ($LASTEXITCODE -ne 0) { throw 'Synthetic workspace fixtures could not be created.' }
}
finally {
  Remove-Item Env:SACCO_ACCEPTANCE_PASSWORD -ErrorAction SilentlyContinue
  Pop-Location
}
