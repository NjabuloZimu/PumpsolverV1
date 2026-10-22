$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pumpPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pumpPython)) {
    throw 'Create the environment first: python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt'
}
& $pumpPython (Join-Path $PSScriptRoot 'callmain.py')
exit $LASTEXITCODE
