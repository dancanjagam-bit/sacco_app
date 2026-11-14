param(
  [string]$Database = (Join-Path $PSScriptRoot '..\.recovery\transport-acceptance\acceptance-final.sqlite3')
)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $Repo 'venv\Scripts\python.exe'
$Database = [System.IO.Path]::GetFullPath($Database)
$DataDirectory = Split-Path -Parent $Database

if (-not (Test-Path -LiteralPath $Python)) { throw "Project virtualenv Python not found: $Python" }
$AllowedRoot = [System.IO.Path]::GetFullPath((Join-Path $Repo '.recovery\transport-acceptance')).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $Database.StartsWith($AllowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw 'Acceptance DB must stay under .recovery\transport-acceptance; existing app databases are not valid targets.'
}
New-Item -ItemType Directory -Force -Path $DataDirectory | Out-Null

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
  if ($LASTEXITCODE -ne 0) { throw 'Acceptance database migration failed.' }
  & $Python manage.py seed_transport_acceptance --settings=sacco.acceptance_settings
  if ($LASTEXITCODE -ne 0) { throw 'Synthetic acceptance data could not be created.' }
}
finally {
  Remove-Item Env:SACCO_ACCEPTANCE_PASSWORD -ErrorAction SilentlyContinue
  Pop-Location
}
