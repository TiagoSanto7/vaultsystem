@echo off
setlocal
set "VS_CLI=1"
set "PYTHONUTF8=1"
py -3 -c "import sys; sys.exit(sys.version_info < (3,8))" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(sys.version_info < (3,8))" >nul 2>&1
if not errorlevel 1 goto use_python
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  "%%~fD\python.exe" -c "import sys; sys.exit(sys.version_info < (3,8))" >nul 2>&1
  if not errorlevel 1 (
    set "VS_PYTHON=%%~fD\python.exe"
    goto use_local
  )
)
echo Instale Python 3.8 ou superior para usar o Vault System. 1>&2
exit /b 1
:use_py
py -3 "%~dp0cli\vs.py" %*
exit /b %errorlevel%
:use_python
python "%~dp0cli\vs.py" %*
exit /b %errorlevel%
:use_local
"%VS_PYTHON%" "%~dp0cli\vs.py" %*
exit /b %errorlevel%
