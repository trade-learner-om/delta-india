@echo off
setlocal EnableExtensions

cd /d "%~dp0..\backend-python"
if not exist "pyproject.toml" (
  echo pyproject.toml not found in %CD%
  exit /b 1
)

set "BACKEND_DIR=%CD%"
call "%~dp0_python_venv_win.bat" find_python
if errorlevel 1 exit /b 1
call "%~dp0_python_venv_win.bat" ensure_venv
if errorlevel 1 exit /b 1

set "VENV_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"

echo Installing CryptoBridge backend dependencies...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_PY%" -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1

echo Verifying python-jose...
"%VENV_PY%" -c "from jose import jwt; print('python-jose OK')"
exit /b %ERRORLEVEL%
