@echo off
setlocal EnableDelayedExpansion

rem Watches MongoDB and starts it when stopped.
rem Usage: scripts\watch-mongodb.bat [watch^|start^|stop^|status^|once]
rem
rem Environment (optional):
rem   MONGODB_SERVICE_NAME   Windows service name (default: MongoDB)
rem   MONGODB_PORT           TCP port (default: 27017)
rem   MONGODB_WATCH_INTERVAL Seconds between checks in watch mode (default: 10)
rem   MONGODB_BIN            Full path to mongod.exe if not using a service
rem   MONGODB_DBPATH         Data directory when starting mongod directly
rem   MONGODB_LOG_PATH       Log file when starting mongod directly

cd /d "%~dp0.."
set "ROOT=%CD%"
set "RUN_DIR=%ROOT%\.run"
set "PID_FILE=%RUN_DIR%\mongodb.pid"
set "LAUNCH_FILE=%RUN_DIR%\mongodb-launch.bat"

set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=watch"

if not defined MONGODB_SERVICE_NAME set "MONGODB_SERVICE_NAME=MongoDB"
if not defined MONGODB_PORT set "MONGODB_PORT=27017"
if not defined MONGODB_WATCH_INTERVAL set "MONGODB_WATCH_INTERVAL=10"
if not defined MONGODB_DBPATH set "MONGODB_DBPATH=%ROOT%\data\mongodb"
if not defined MONGODB_LOG_PATH set "MONGODB_LOG_PATH=%ROOT%\data\mongodb\mongod.log"

if /i not "%ACTION%"=="watch" if /i not "%ACTION%"=="start" if /i not "%ACTION%"=="stop" if /i not "%ACTION%"=="status" if /i not "%ACTION%"=="once" (
  echo Usage: scripts\watch-mongodb.bat [watch^|start^|stop^|status^|once]
  echo   watch  Loop forever; restart MongoDB when it stops ^(default^)
  echo   once   Check once and start if down
  echo   start  Start MongoDB if not already listening
  echo   stop   Stop MongoDB service or mongod on port %MONGODB_PORT%
  echo   status Show whether MongoDB is listening
  exit /b 1
)

if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"

if /i "%ACTION%"=="watch" goto :do_watch
if /i "%ACTION%"=="once" goto :do_once
if /i "%ACTION%"=="start" goto :do_start
if /i "%ACTION%"=="stop" goto :do_stop
if /i "%ACTION%"=="status" goto :do_status
exit /b 1

:mongo_listening
set "LISTENER_PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%MONGODB_PORT% " ^| findstr LISTENING') do (
  set "LISTENER_PID=%%p"
  goto :mongo_listening_done
)
:mongo_listening_done
if defined LISTENER_PID exit /b 0
exit /b 1

:service_exists
set "SERVICE_EXISTS=0"
sc query "%MONGODB_SERVICE_NAME%" >nul 2>&1
if not errorlevel 1 set "SERVICE_EXISTS=1"
exit /b 0

:service_running
call :service_exists
if "!SERVICE_EXISTS!"=="0" exit /b 1
for /f "tokens=3" %%s in ('sc query "%MONGODB_SERVICE_NAME%" ^| findstr /I "STATE"') do (
  if /i "%%s"=="RUNNING" exit /b 0
)
exit /b 1

:find_mongod_bin
set "MONGOD_BIN="
if defined MONGODB_BIN (
  if exist "%MONGODB_BIN%" (
    set "MONGOD_BIN=%MONGODB_BIN%"
    exit /b 0
  )
)
for /f "delims=" %%m in ('where mongod 2^>nul') do (
  set "MONGOD_BIN=%%m"
  goto :find_mongod_bin_done
)
if exist "C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe" set "MONGOD_BIN=C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe"
if not defined MONGOD_BIN if exist "C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe" set "MONGOD_BIN=C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe"
if not defined MONGOD_BIN if exist "C:\Program Files\MongoDB\Server\6.0\bin\mongod.exe" set "MONGOD_BIN=C:\Program Files\MongoDB\Server\6.0\bin\mongod.exe"
:find_mongod_bin_done
if defined MONGOD_BIN exit /b 0
exit /b 1

:write_launcher
if not exist "%MONGODB_DBPATH%" mkdir "%MONGODB_DBPATH%"
for %%D in ("%MONGODB_DBPATH%") do set "MONGODB_DBPATH=%%~fD"
for %%D in ("%MONGODB_LOG_PATH%") do set "MONGODB_LOG_PATH=%%~fD"
(
  echo @echo off
  echo echo Starting mongod on port %MONGODB_PORT%...
  echo "%MONGOD_BIN%" --dbpath "%MONGODB_DBPATH%" --logpath "%MONGODB_LOG_PATH%" --port %MONGODB_PORT%
) > "%LAUNCH_FILE%"
exit /b 0

:wait_for_mongo
set "READY=0"
for /l %%i in (1,1,30) do (
  timeout /t 1 /nobreak >nul
  call :mongo_listening
  if not errorlevel 1 (
    set "READY=1"
    goto :wait_for_mongo_done
  )
)
:wait_for_mongo_done
if "!READY!"=="0" exit /b 1
exit /b 0

:start_mongo
call :mongo_listening
if not errorlevel 1 (
  echo MongoDB is already listening on port %MONGODB_PORT% ^(pid !LISTENER_PID!^).
  echo !LISTENER_PID!>"%PID_FILE%"
  exit /b 0
)

call :service_exists
if "!SERVICE_EXISTS!"=="1" (
  echo Starting MongoDB Windows service "%MONGODB_SERVICE_NAME%"...
  net start "%MONGODB_SERVICE_NAME%" >nul 2>&1
  if errorlevel 1 (
    echo Failed to start service "%MONGODB_SERVICE_NAME%". Try running this script as Administrator.
    exit /b 1
  )
  call :wait_for_mongo
  if errorlevel 1 (
    echo Service started but port %MONGODB_PORT% is not listening yet.
    exit /b 1
  )
  call :mongo_listening
  if defined LISTENER_PID echo !LISTENER_PID!>"%PID_FILE%"
  echo MongoDB service is running on port %MONGODB_PORT%.
  exit /b 0
)

call :find_mongod_bin
if errorlevel 1 (
  echo MongoDB is not running and no service or mongod.exe was found.
  echo Install MongoDB as a Windows service, or set MONGODB_BIN to mongod.exe.
  exit /b 1
)

call :write_launcher
echo Starting mongod in a new window...
start "MongoDB" cmd /k call "%LAUNCH_FILE%"
call :wait_for_mongo
if errorlevel 1 (
  echo mongod did not start listening on port %MONGODB_PORT% within 30s.
  echo Check the "MongoDB" window for errors.
  exit /b 1
)
call :mongo_listening
if defined LISTENER_PID echo !LISTENER_PID!>"%PID_FILE%"
echo MongoDB is listening on mongodb://localhost:%MONGODB_PORT%/cryptobridge
exit /b 0

:do_once
call :start_mongo
exit /b %ERRORLEVEL%

:do_start
call :start_mongo
exit /b %ERRORLEVEL%

:do_watch
echo Watching MongoDB on port %MONGODB_PORT% every %MONGODB_WATCH_INTERVAL%s. Press Ctrl+C to stop.
:watch_loop
call :mongo_listening
if errorlevel 1 (
  echo [%date% %time%] MongoDB is down. Starting...
  call :start_mongo
  if errorlevel 1 (
    echo [%date% %time%] Start attempt failed. Retrying in %MONGODB_WATCH_INTERVAL%s.
  ) else (
    echo [%date% %time%] MongoDB is up.
  )
) else (
  echo [%date% %time%] MongoDB ok ^(pid !LISTENER_PID!^).
  echo !LISTENER_PID!>"%PID_FILE%"
)
timeout /t %MONGODB_WATCH_INTERVAL% /nobreak >nul
goto :watch_loop

:do_stop
set "STOPPED=0"

call :service_running
if not errorlevel 1 (
  echo Stopping MongoDB service "%MONGODB_SERVICE_NAME%"...
  net stop "%MONGODB_SERVICE_NAME%" >nul 2>&1
  if not errorlevel 1 set "STOPPED=1"
)

call :mongo_listening
if defined LISTENER_PID (
  echo Stopping mongod on port %MONGODB_PORT% ^(pid !LISTENER_PID!^)...
  taskkill /PID !LISTENER_PID! /T /F >nul 2>&1
  set "STOPPED=1"
)

if exist "%PID_FILE%" del /f /q "%PID_FILE%" >nul 2>&1

if "!STOPPED!"=="0" (
  echo MongoDB is not running on port %MONGODB_PORT%.
  exit /b 0
)

echo MongoDB stopped.
exit /b 0

:do_status
echo MongoDB status ^(port %MONGODB_PORT%^)
call :mongo_listening
if not errorlevel 1 (
  echo mongo: listening ^(pid !LISTENER_PID!^)
  echo uri:  mongodb://localhost:%MONGODB_PORT%/cryptobridge
  exit /b 0
)

call :service_running
if not errorlevel 1 (
  echo mongo: service running but port %MONGODB_PORT% is not listening
  exit /b 1
)

echo mongo: stopped
if exist "%PID_FILE%" del /f /q "%PID_FILE%" >nul 2>&1
exit /b 1
