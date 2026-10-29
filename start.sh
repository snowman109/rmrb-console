#!/usr/bin/env bash
# 一键启动 / 重启 AVD 归因控制台（本地单机）
#
#   ./start.sh              启动；若已在跑则先停再起（= 重启）
#   ./start.sh stop         停止（连同被它拉起的 avd_rounds.py 一起收掉）
#   ./start.sh status       看状态
#   ./start.sh logs         跟踪日志
#   ./start.sh --no-build   跳过前端构建（改过前端就别用）
#   ./start.sh --port 9000  换端口
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd -P)
HOST=127.0.0.1
PORT=${PORT:-8787}
PYTHON=${PYTHON:-python3}
ACTION=start
BUILD=1

while [ $# -gt 0 ]; do
  case "$1" in
    start|stop|restart|status|logs) ACTION=$1 ;;
    --no-build) BUILD=0 ;;
    --port) PORT=$2; shift ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数: $1（-h 看用法）" >&2; exit 2 ;;
  esac
  shift
done
[ "$ACTION" = restart ] && ACTION=start

export AVD_CONSOLE_DATA=${AVD_CONSOLE_DATA:-$ROOT/data}
DATA=$AVD_CONSOLE_DATA
PID_FILE=$DATA/.server.pid
LOG_FILE=$DATA/server.log
mkdir -p "$DATA"

say() { printf '%s\n' "$*"; }
die() { printf '错误: %s\n' "$*" >&2; exit 1; }

server_pid() {
  # pid 文件优先；pid 文件丢了就按监听端口找回本项目自己的 uvicorn
  if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null \
       && ps -o command= -p "$pid" 2>/dev/null | grep -q 'uvicorn app.main:app'; then
      echo "$pid"; return 0
    fi
  fi
  if command -v lsof >/dev/null 2>&1; then
    for pid in $(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null || true); do
      if ps -o command= -p "$pid" 2>/dev/null | grep -q 'uvicorn app.main:app'; then
        echo "$pid"; return 0
      fi
    done
  fi
  return 1
}

script_pids() {
  # 控制台拉起的脚本子进程走 start_new_session，停服务不会带走它，这里单独收
  path=$("$PYTHON" - <<PY 2>/dev/null || true
import json, pathlib
p = pathlib.Path("$DATA/config.json")
print(json.loads(p.read_text())["script_path"] if p.exists() else "")
PY
)
  [ -n "${path:-}" ] || return 0
  pgrep -f "$path" 2>/dev/null || true
}

stop_all() {
  stopped=0
  if pid=$(server_pid); then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -9 "$pid" 2>/dev/null || true
    say "已停止服务 (pid $pid)"
    stopped=1
  fi
  rm -f "$PID_FILE"

  pids=$(script_pids)
  if [ -n "$pids" ]; then
    say "发现仍在跑的采集脚本，一并停止：$(echo $pids | tr '\n' ' ')"
    for pid in $pids; do kill "$pid" 2>/dev/null || true; done
    for _ in $(seq 1 20); do
      alive=0
      for pid in $pids; do kill -0 "$pid" 2>/dev/null && alive=1; done
      [ "$alive" = 0 ] && break
      sleep 0.25
    done
    for pid in $pids; do kill -9 "$pid" 2>/dev/null || true; done
    say "对应运行会在下次启动时标记为 interrupted"
    stopped=1
  fi

  [ "$stopped" = 1 ] || say "服务未在运行"
}

needs_build() {
  [ "$BUILD" = 1 ] || return 1
  dist=$ROOT/frontend/dist/index.html
  [ -f "$dist" ] || return 0
  [ -n "$(find "$ROOT/frontend/src" "$ROOT/frontend/index.html" "$ROOT/frontend/package.json" \
            -newer "$dist" -print -quit 2>/dev/null)" ]
}

build_frontend() {
  command -v npm >/dev/null 2>&1 || die "找不到 npm，无法构建前端；装好 Node 或加 --no-build"
  if [ ! -d "$ROOT/frontend/node_modules" ]; then
    say "安装前端依赖 ..."
    ( cd "$ROOT/frontend" && npm install )
  fi
  say "构建前端 ..."
  ( cd "$ROOT/frontend" && npm run build )
}

start_server() {
  command -v "$PYTHON" >/dev/null 2>&1 || die "找不到 $PYTHON"
  "$PYTHON" -c 'import fastapi, uvicorn' 2>/dev/null \
    || die "$PYTHON 里没装 fastapi/uvicorn，先 pip install -r backend/requirements.txt"
  [ -d "$ROOT/frontend/dist" ] || die "frontend/dist 不存在，去掉 --no-build 让我先构建"

  if command -v lsof >/dev/null 2>&1 && [ -n "$(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null || true)" ]; then
    die "端口 $PORT 被别的程序占着（不是本项目 uvicorn），换 --port 或先腾出来"
  fi

  cd "$ROOT"
  : > "$LOG_FILE"
  nohup "$PYTHON" -m uvicorn app.main:app --app-dir backend \
        --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"

  for _ in $(seq 1 40); do
    if ! kill -0 "$pid" 2>/dev/null; then
      tail -n 20 "$LOG_FILE" >&2 || true
      die "服务启动后立即退出，日志在上面（$LOG_FILE）"
    fi
    curl -sf "http://$HOST:$PORT/api/config" >/dev/null 2>&1 && break
    sleep 0.5
  done
  curl -sf "http://$HOST:$PORT/api/config" >/dev/null 2>&1 \
    || { tail -n 20 "$LOG_FILE" >&2 || true; die "20 秒内没起来，日志：$LOG_FILE"; }

  say "已启动 (pid $pid)"
  say "打开 http://$HOST:$PORT"
  say "日志: ./start.sh logs    停止: ./start.sh stop"
}

case "$ACTION" in
  start)
    stop_all
    if needs_build; then build_frontend; fi
    start_server
    ;;
  stop) stop_all ;;
  status)
    if pid=$(server_pid); then
      say "运行中 (pid $pid) → http://$HOST:$PORT"
      curl -sf "http://$HOST:$PORT/api/config" >/dev/null 2>&1 \
        && say "健康检查: OK" || say "健康检查: 端口通但 /api/config 没响应"
    else
      say "未运行"
    fi
    pids=$(script_pids)
    if [ -n "$pids" ]; then
      say "采集脚本仍在跑: $(echo $pids | tr '\n' ' ')"
    fi
    ;;
  logs) touch "$LOG_FILE"; tail -f "$LOG_FILE" ;;
esac