#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend-python"
RUN_DIR="$ROOT/.run"
PID_FILE="$RUN_DIR/backend.pid"
PORT_FILE="$RUN_DIR/backend.port"
ACTION="${1:-start}"
BACKEND_PORT="${PORT:-8080}"
MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017/cryptobridge}"

mkdir -p "$RUN_DIR"

if [[ ! -f "$BACKEND_DIR/pyproject.toml" ]]; then
  echo "Python backend pyproject.toml not found at $BACKEND_DIR" >&2
  exit 1
fi

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$port" >/dev/null 2>&1
    return $?
  fi
  return 1
}

pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

read_pid() {
  if [[ -f "$PID_FILE" ]]; then
    tr -d '[:space:]' < "$PID_FILE"
  fi
}

load_port() {
  if [[ -f "$PORT_FILE" ]]; then
    BACKEND_PORT="$(tr -d '[:space:]' < "$PORT_FILE")"
  fi
  BACKEND_PORT="${PORT:-$BACKEND_PORT}"
}

health_ready() {
  local port="$1"
  local url="http://localhost:${port}/api/health"
  if command -v curl >/dev/null 2>&1; then
    curl -sf "$url" >/dev/null 2>&1
    return $?
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO- "$url" >/dev/null 2>&1
    return $?
  fi
  return 1
}

show_health() {
  local port="$1"
  local url="http://localhost:${port}/api/health"
  if command -v curl >/dev/null 2>&1; then
    curl -sf "$url"
    echo
    echo "Health check passed: $url"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO- "$url"
    echo
    echo "Health check passed: $url"
    return 0
  fi
  echo "curl or wget is required to check backend health." >&2
  return 1
}

ensure_venv() {
  if [[ -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found in PATH." >&2
    exit 1
  fi
  cd "$BACKEND_DIR"
  if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment in backend-python/.venv"
    python3 -m venv .venv
  fi
  echo "Installing backend dependencies..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -e ".[dev]"
}

show_access_urls() {
  local port="$1"
  echo "API:     http://localhost:${port}/api"
  echo "Health:  http://localhost:${port}/api/health"
  echo "Public:  http://0.0.0.0:${port}/api (all interfaces)"
  local lan_ip=""
  if command -v ipconfig >/dev/null 2>&1; then
    lan_ip="$(ipconfig 2>/dev/null | grep -Eo 'IPv4[^:]*: [0-9.]+' | head -1 | grep -Eo '[0-9.]+$' || true)"
  fi
  if [[ -z "$lan_ip" ]] && command -v hostname >/dev/null 2>&1; then
    lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  if [[ -n "$lan_ip" ]]; then
    echo "LAN:     http://${lan_ip}:${port}/api"
    echo "Frontend: http://${lan_ip}:5173 (run npm run dev in frontend-react)"
  fi
  echo "Open firewall for ports ${port} and 5173 if accessing remotely."
}

start_backend() {
  ensure_venv
  local pid
  pid="$(read_pid)"

  if [[ -n "${PORT:-}" ]]; then
    BACKEND_PORT="$PORT"
  elif [[ -f "$PORT_FILE" ]]; then
    BACKEND_PORT="$(tr -d '[:space:]' < "$PORT_FILE")"
  else
    BACKEND_PORT="8080"
  fi

  if port_in_use "$BACKEND_PORT" || pid_running "$pid"; then
    echo "CryptoBridge backend is already running on port $BACKEND_PORT."
    status_backend
    return 0
  fi

  echo "Starting CryptoBridge backend on port $BACKEND_PORT"
  # App logs go to logs/cryptobridge.log (tail -f logs/cryptobridge.log).
  # Do not shell-redirect stdout here — that would duplicate file output.
  nohup bash -c "cd \"$BACKEND_DIR\" && MONGODB_URI=\"$MONGODB_URI\" PORT=\"$BACKEND_PORT\" .venv/bin/python -m cryptobridge.server" \
    >/dev/null 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"
  echo "$BACKEND_PORT" > "$PORT_FILE"

  for _ in {1..60}; do
    if health_ready "$BACKEND_PORT"; then
      echo "Backend started (pid $pid)."
      echo "Tail logs: tail -f \"$ROOT/logs/cryptobridge.log\""
      show_access_urls "$BACKEND_PORT"
      show_health "$BACKEND_PORT"
      return 0
    fi
    sleep 1
  done

  echo "Backend did not become healthy on port $BACKEND_PORT." >&2
  echo "Check that MongoDB is running on mongodb://localhost:27017" >&2
  return 1
}

stop_backend() {
  load_port
  local pid
  pid="$(read_pid)"
  if pid_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
    for _ in {1..20}; do
      if ! pid_running "$pid"; then
        rm -f "$PID_FILE" "$PORT_FILE"
        echo "Stopped backend."
        return 0
      fi
      sleep 0.5
    done
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$PID_FILE" "$PORT_FILE"
  echo "Backend is not running."
}

status_backend() {
  load_port
  local pid
  pid="$(read_pid)"
  echo "CryptoBridge backend status"
  if pid_running "$pid" || port_in_use "$BACKEND_PORT" || health_ready "$BACKEND_PORT"; then
    echo "backend: running (pid ${pid:-unknown}) on port $BACKEND_PORT"
    show_access_urls "$BACKEND_PORT"
    if health_ready "$BACKEND_PORT"; then
      echo "health:  ok"
      return 0
    fi
    echo "health:  check failed"
    return 1
  fi
  echo "backend: stopped"
  return 1
}

case "$ACTION" in
  start) start_backend ;;
  stop) stop_backend ;;
  restart) stop_backend; start_backend ;;
  status) status_backend ;;
  *)
    echo "Usage: ./scripts/run-backend.sh {start|stop|restart|status}" >&2
    exit 1
    ;;
esac
