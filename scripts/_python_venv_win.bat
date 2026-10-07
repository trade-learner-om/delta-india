@echo off
REM Shared Python + venv helpers for Windows batch scripts.
REM Usage: call "%~dp0_python_venv_win.bat" find_python
REM        call "%~dp0_python_venv_win.bat" ensure_venv

if /i "%~1"=="find_python" goto :find_python
if /i "%~1"=="ensure_venv" goto :ensure_venv
exit /b 1

:find_python
set "PYTHON_ARGS="
for %%V in (3.13 3.12 3.11 3.10 3.9) do (
  if not defined PYTHON_ARGS (
    py -%%V --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_ARGS=py -%%V"
  )
)
if not defined PYTHON_ARGS where python >nul 2>nul && python --version >nul 2>&1 && set "PYTHON_ARGS=python"
if not defined PYTHON_ARGS where py >nul 2>nul && py -3 --version >nul 2>&1 && set "PYTHON_ARGS=py -3"
if not defined PYTHON_ARGS where py >nul 2>nul && py --version >nul 2>&1 && set "PYTHON_ARGS=py"
if not defined PYTHON_ARGS (
  echo Python 3.9+ is required. Install from https://www.python.org/downloads/ or run: py --list
  exit /b 1
)
exit /b 0

:ensure_venv
if not defined BACKEND_DIR set "BACKEND_DIR=%CD%"
set "VENV_DIR=%BACKEND_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if exist "%VENV_PY%" (
  "%VENV_PY%" --version >nul 2>&1
  if errorlevel 1 goto :recreate_venv
  "%VENV_PY%" -m pip --version >nul 2>&1
  if not errorlevel 1 exit /b 0
  "%VENV_PY%" -m ensurepip --upgrade >nul 2>&1
  if not errorlevel 1 exit /b 0
  goto :recreate_venv
)

if not exist "%VENV_PY%" goto :create_venv
exit /b 0

:recreate_venv
echo Virtual environment is broken or points to a removed Python install.
echo Removing %VENV_DIR% ...
rmdir /s /q "%VENV_DIR%" 2>nul

:create_venv
if not defined PYTHON_ARGS (
  echo PYTHON_ARGS is not set. Call find_python first.
  exit /b 1
)
echo Creating virtual environment with %PYTHON_ARGS% ...
%PYTHON_ARGS% --version
if errorlevel 1 exit /b 1
cd /d "%BACKEND_DIR%"
%PYTHON_ARGS% -m venv .venv
if errorlevel 1 exit /b 1
if not exist "%VENV_PY%" (
  echo Failed to create %VENV_PY%
  exit /b 1
)
"%VENV_PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo Bootstrapping pip...
  "%VENV_PY%" -m ensurepip --upgrade
  if errorlevel 1 exit /b 1
)
exit /b 0
