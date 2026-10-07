@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0.."
set "ROOT=%CD%"
set "BACKEND_DIR=%ROOT%\backend-python"
set "RUN_DIR=%ROOT%\.run"
set "PID_FILE=%RUN_DIR%\backend.pid"
set "PORT_FILE=%RUN_DIR%\backend.port"
set "LAUNCH_FILE=%RUN_DIR%\backend-launch.bat"
set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=start"

if /i not "%ACTION%"=="start" if /i not "%ACTION%"=="stop" if /i not "%ACTION%"=="restart" if /i not "%ACTION%"=="status" (
  echo Usage: scripts\run-backend.bat {start^|stop^|restart^|status}
  exit /b 1
)

if not exist "%BACKEND_DIR%\pyproject.toml" (
  echo Python backend pyproject.toml not found at %BACKEND_DIR%
  exit /b 1
)

if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"

if /i "%ACTION%"=="start" goto :do_start
if /i "%ACTION%"=="stop" goto :do_stop
if /i "%ACTION%"=="restart" goto :do_restart
if /i "%ACTION%"=="status" goto :do_status
exit /b 1

:ensure_venv
call "%~dp0_python_venv_win.bat" find_python
if errorlevel 1 exit /b 1
call "%~dp0_python_venv_win.bat" ensure_venv
if errorlevel 1 exit /b 1

cd /d "%BACKEND_DIR%"
set "VENV_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"

echo Syncing backend dependencies...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_PY%" -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1
exit /b 0

:load_port
set "PORT="
if exist "%PORT_FILE%" set /p PORT=<"%PORT_FILE%"
if not defined PORT set "PORT=8080"
exit /b 0

:find_listener_pid
set "LISTENER_PID="
set "CHECK_PORT=%~1"
for /f %%p in ('powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort %CHECK_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if ($c) { $c }"') do (
  set "LISTENER_PID=%%p"
  goto :find_listener_pid_done
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /C:":%CHECK_PORT%" ^| findstr LISTENING') do (
  set "LISTENER_PID=%%p"
  goto :find_listener_pid_done
)
:find_listener_pid_done
exit /b 0

:health_ready
set "CHECK_PORT=%~1"
set "HEALTH_URL=http://localhost:%CHECK_PORT%/api/health"
where curl >nul 2>nul && curl -sf "%HEALTH_URL%" >nul 2>&1 && exit /b 0
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing '%HEALTH_URL%'; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b %ERRORLEVEL%

:show_health
set "CHECK_PORT=%~1"
set "HEALTH_URL=http://localhost:%CHECK_PORT%/api/health"
where curl >nul 2>nul && (
  curl -sf "%HEALTH_URL%"
  if not errorlevel 1 (
    echo.
    echo Health check passed: %HEALTH_URL%
    exit /b 0
  )
)
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing '%HEALTH_URL%'; Write-Host $r.Content; Write-Host ''; Write-Host 'Health check passed: %HEALTH_URL%' } catch { exit 1 }"
exit /b %ERRORLEVEL%

:show_access_urls
set "ACCESS_PORT=%~1"
echo API:     http://localhost:%ACCESS_PORT%/api
echo Health:  http://localhost:%ACCESS_PORT%/api/health
echo Public:  http://0.0.0.0:%ACCESS_PORT%/api ^(all interfaces^)
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$ip = (Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object { $_.IPAddress -notlike '127.*' } ^| Select-Object -First 1 -ExpandProperty IPAddress); if ($ip) { $ip }"`) do (
  echo LAN:     http://%%i:%ACCESS_PORT%/api
  echo Frontend: http://%%i:5173 ^(run npm run dev in frontend-react^)
)
echo Open Windows Firewall for ports %ACCESS_PORT% and 5173 if accessing remotely.
exit /b 0

:write_launcher
(
  echo @echo off
  echo cd /d "%BACKEND_DIR%"
  echo set "MONGODB_URI=%MONGODB_URI%"
  echo set "PORT=%PORT%"
  echo rem Logs go to logs/cryptobridge.log only ^(tail -f in Git Bash^).
  echo echo Starting CryptoBridge backend on port %%PORT%%...
  echo "%BACKEND_DIR%\.venv\Scripts\python.exe" -m cryptobridge.server
) > "%LAUNCH_FILE%"
exit /b 0

:do_start
call :ensure_venv
if errorlevel 1 exit /b 1

if not defined PORT set "PORT=8080"
if not defined MONGODB_URI set "MONGODB_URI=mongodb://localhost:27017/cryptobridge"

call :find_listener_pid %PORT%
if defined LISTENER_PID (
  echo CryptoBridge backend is already running on port %PORT% ^(pid !LISTENER_PID!^).
  echo !LISTENER_PID!>"%PID_FILE%"
  echo %PORT%>"%PORT_FILE%"
  call :do_status
  exit /b 0
)

call :write_launcher
echo Starting CryptoBridge backend on port %PORT% in a new window...
start "CryptoBridge Backend" cmd /k call "%LAUNCH_FILE%"
echo %PORT%>"%PORT_FILE%"

echo Waiting for server to respond ^(up to 60s^)...
set "READY=0"
for /l %%i in (1,1,60) do (
  timeout /t 1 /nobreak >nul
  call :health_ready %PORT%
  if not errorlevel 1 (
    set "READY=1"
    goto :start_ready
  )
)
:start_ready
if "!READY!"=="0" (
  echo Backend did not become healthy on port %PORT%.
  echo Check the "CryptoBridge Backend" window for errors.
  echo Common fix: start MongoDB on mongodb://localhost:27017
  exit /b 1
)

call :find_listener_pid %PORT%
if defined LISTENER_PID echo !LISTENER_PID!>"%PID_FILE%"
echo Backend window opened.
echo Tail logs: tail -f "%ROOT%\logs\cryptobridge.log"
call :show_access_urls %PORT%
call :show_health %PORT%
exit /b %ERRORLEVEL%

:do_stop
call :load_port
call :find_listener_pid %PORT%
if not defined LISTENER_PID (
  if exist "%PID_FILE%" del /f /q "%PID_FILE%" >nul 2>&1
  if exist "%PORT_FILE%" del /f /q "%PORT_FILE%" >nul 2>&1
  echo Backend is not running.
  exit /b 0
)

echo Stopping backend on port %PORT% ^(pid !LISTENER_PID!^)...
taskkill /PID !LISTENER_PID! /T /F >nul 2>&1
set "STOPPED=0"
for /l %%i in (1,1,20) do (
  call :find_listener_pid %PORT%
  if not defined LISTENER_PID (
    set "STOPPED=1"
    goto :stop_done
  )
  timeout /t 1 /nobreak >nul
)
:stop_done
if "!STOPPED!"=="0" (
  echo Failed to stop backend on port %PORT%.
  exit /b 1
)
if exist "%PID_FILE%" del /f /q "%PID_FILE%" >nul 2>&1
if exist "%PORT_FILE%" del /f /q "%PORT_FILE%" >nul 2>&1
echo Stopped backend.
exit /b 0

:do_restart
call :do_stop
call :do_start
exit /b %ERRORLEVEL%

:do_status
call :load_port
call :find_listener_pid %PORT%
echo CryptoBridge backend status
if defined LISTENER_PID (
  echo backend: running ^(pid !LISTENER_PID!^) on port %PORT%
  goto :status_health
)
call :health_ready %PORT%
if not errorlevel 1 (
  echo backend: running on port %PORT% ^(pid unknown^)
  goto :status_health
)
echo backend: stopped
if exist "%PID_FILE%" del /f /q "%PID_FILE%" >nul 2>&1
exit /b 1

:status_health
call :show_access_urls %PORT%
call :health_ready %PORT%
if errorlevel 1 (
  echo health:  check failed
  exit /b 1
)
echo health:  ok
exit /b 0
