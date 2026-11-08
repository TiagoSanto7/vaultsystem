# Instalador da VS CLI (Vault System) para Windows.
#
#   irm {{HUB}}/v1/cli/install.ps1 | iex
#
# Baixa a CLI deste hub para %LOCALAPPDATA%\VaultSystem, cria os comandos `vs` e
# `vaultsystem` em %LOCALAPPDATA%\VaultSystem\bin e põe essa pasta no PATH do seu
# usuário (não precisa de administrador). Já deixa o endereço do hub configurado:
# depois é só `vs login` e colar o token de conexão.
#
# Variáveis opcionais: VS_HUB (outro hub), VS_INSTALL_DIR (outra pasta),
# VS_NO_PATH=1 (não mexe no PATH).
$ErrorActionPreference = 'Stop'
$Hub = if ($env:VS_HUB) { $env:VS_HUB.TrimEnd('/') } else { '{{HUB}}' }
$Dir = if ($env:VS_INSTALL_DIR) { $env:VS_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'VaultSystem' }
$Bin = Join-Path $Dir 'bin'

function Test-Python([string]$exe, [string[]]$extra) {
  try {
    & $exe @extra -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}
if (-not ((Test-Python 'py' @('-3')) -or (Test-Python 'python' @()) -or (Test-Python 'python3' @()))) {
  Write-Host 'A VS CLI precisa do Python 3.8 ou mais novo: https://www.python.org/downloads/ (marque "Add python.exe to PATH").' -ForegroundColor Yellow
  throw 'Python 3.8+ não encontrado.'
}

New-Item -ItemType Directory -Force -Path $Bin | Out-Null
$script = Join-Path $Dir 'vs.py'
Write-Host "Baixando a VS CLI de $Hub ..."
Invoke-WebRequest -UseBasicParsing -Uri "$Hub/v1/cli/vs" -OutFile "$script.novo"
$inicio = Get-Content -Path "$script.novo" -TotalCount 1
if ($inicio -notlike '#!*python*') { Remove-Item "$script.novo"; throw "O hub $Hub não devolveu a CLI." }
Move-Item -Force "$script.novo" $script

$shim = @'
@echo off
setlocal
set "VS_CLI=1"
set "PYTHONUTF8=1"
set "VS_PY=%~dp0..\vs.py"
py -3 -c "import sys; sys.exit(sys.version_info < (3,8))" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(sys.version_info < (3,8))" >nul 2>&1
if not errorlevel 1 goto use_python
echo Instale o Python 3.8 ou mais novo para usar o Vault System. 1>&2
exit /b 1
:use_py
py -3 "%VS_PY%" __ARGS__
exit /b %errorlevel%
:use_python
python "%VS_PY%" __ARGS__
exit /b %errorlevel%
'@
Set-Content -Path (Join-Path $Bin 'vs.cmd') -Value ($shim -replace '__ARGS__', '%*') -Encoding ASCII
Set-Content -Path (Join-Path $Bin 'vaultsystem.cmd') -Value ($shim -replace '__ARGS__', 'welcome %*') -Encoding ASCII

# Endereço do hub na configuração da CLI (o token vem no vs login).
$cfgBase = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $env:USERPROFILE '.config' }
$cfgDir = Join-Path $cfgBase 'vaultsystem'
$cfg = Join-Path $cfgDir 'config.json'
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$dados = @{}
if (Test-Path $cfg) {
  try { (Get-Content $cfg -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $dados[$_.Name] = $_.Value } } catch {}
}
if (-not $dados['url']) { $dados['url'] = $Hub }
$json = $dados | ConvertTo-Json
[System.IO.File]::WriteAllText($cfg, $json, (New-Object System.Text.UTF8Encoding $false))

if ($env:VS_NO_PATH -ne '1') {
  $atual = [Environment]::GetEnvironmentVariable('Path', 'User')
  $partes = @($atual -split ';' | Where-Object { $_ })
  if ($partes -notcontains $Bin) {
    [Environment]::SetEnvironmentVariable('Path', (($partes + $Bin) -join ';'), 'User')
    Write-Host "Pasta adicionada ao PATH do seu usuário: $Bin"
  }
  if (($env:Path -split ';') -notcontains $Bin) { $env:Path = "$env:Path;$Bin" }
}

Write-Host ''
Write-Host 'VS CLI instalada.' -ForegroundColor Cyan
Write-Host "  vs login          conecta ao hub $Hub (cole o token de conexão da aba Tokens)"
Write-Host '  vs init vault=<name>, then vs sync'
Write-Host '  vaultsystem       o painel de boas-vindas'
Write-Host 'Abra um terminal novo se o comando vs ainda não for encontrado.'
