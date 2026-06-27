"""
猜历史人物 · 单 exe 启动器

打包后入口。职责：
  1. 把内置运行时资源（三个 app + 知识库）释放到稳定工作目录，
     保证 people_db / prompts 的相对路径在该目录下可用。
  2. 在本地 127.0.0.1 起一个极简 HTTP 服务托管 frontend/index.html 首页。
  3. 接收 /api/launch 请求 → 注入 LLM Key 到子进程环境 →
     以派生子进程方式启动对应 streamlit app（复用本 exe，
     argv[1]=="--streamlit-worker" 触发 streamlit.web.cli 直接运行）→
     用默认浏览器打开该 streamlit 地址。
  4. 阻塞主进程，退出时回收所有 game 子进程。

打包：见 build_exe.bat / build_exe.spec
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import socket
import threading
import subprocess
import webbrowser
import time
import atexit
import traceback
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# =========================
# 路径常量
# =========================
APP_TITLE = "猜历史人物"
APP_DIRNAME = "GuessHistory"

#: 需要释放到工作目录的运行时文件（相对于打包根 / 源根）
# 注意：三个 app 顶层会 import prompts/game_state/people_db/fact_checker/llm_client/config
# 这些纯 Python 支撑模块必须一并释放到 runtime 目录，否则脚本 exec 立即 ModuleNotFoundError。
RUNTIME_FILES = [
    # app 入口
    "app.py",
    "app_03_mini.py",
    "app_03_ming.py",
    # 支撑模块（顶层）
    "config.py",
    "game_state.py",
    "people_db.py",
    "fact_checker.py",
    "llm_client.py",
    # 支撑包 prompts（仅 .py；md/ 只是文档，运行时不读）
    os.path.join("prompts", "__init__.py"),
    os.path.join("prompts", "builder.py"),
    os.path.join("prompts", "persona.py"),
    os.path.join("prompts", "rules.py"),
    os.path.join("prompts", "state.py"),
    os.path.join("prompts", "hint.py"),
    os.path.join("prompts", "output.py"),
    os.path.join("prompts", "tools.py"),
    os.path.join("prompts", "fact_check.py"),
    os.path.join("prompts", "recheck.py"),
    # 知识库数据
    "peoples_names.md",
    "top200_famous_people.csv",
    "明朝名人二百人表 - 明朝名人二百人表.csv",
    os.path.join("data", "people.json"),
]

#: 释放后必须存在的关键文件（自检清单）
CRITICAL_FILES = [
    "prompts/__init__.py",
    "game_state.py",
    "llm_client.py",
    "people_db.py",
    "fact_checker.py",
    "config.py",
]

 #: 派生 streamlit worker 的命令标识
WORKER_FLAG = "--streamlit-worker"


def resource_root() -> str:
    """打包后 _MEIPASS / 开发态脚本目录。"""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def frontend_html_path() -> str:
    return os.path.join(resource_root(), "index.html")


def runtime_work_dir() -> str:
    """持久工作目录：LOCALAPPDATA\\GuessHistory\\runtime"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIRNAME, "runtime")
    os.makedirs(path, exist_ok=True)
    return path


def ensure_runtime_files() -> str:
    """把内置文件复制到工作目录（覆盖）。返回工作目录路径。

    释放后做关键文件自检；缺失则抛 RuntimeError，由上层提示用户重新下载。
    """
    root = resource_root()
    dst = runtime_work_dir()
    missing_src = []
    for rel in RUNTIME_FILES:
        src = os.path.join(root, rel)
        if os.path.isdir(src):
            continue  # 仅处理文件
        target = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not os.path.isfile(src):
            sys.stderr.write(f"[launcher] missing bundled file: {rel}\n")
            missing_src.append(rel)
            continue
        shutil.copyfile(src, target)

    # 自检：关键支撑模块必须齐全，否则 app 一执行就 ModuleNotFoundError
    critical_missing = []
    for rel in CRITICAL_FILES:
        if not os.path.isfile(os.path.join(dst, rel.replace("/", os.sep))):
            critical_missing.append(rel)
    if critical_missing:
        msg = (
            "内置资源损坏，缺少关键文件：\n  - "
            + "\n  - ".join(critical_missing)
            + "\n请重新下载 GuessHistory.exe。"
        )
        sys.stderr.write("[launcher] " + msg + "\n")
        raise RuntimeError(msg)
    return dst


# =========================
# 端口分配
# =========================
def find_free_port(start: int = 8501, count: int = 64) -> int:
    for p in range(start, start + count):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", p))
                return p
        except OSError:
            continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# =========================
# 游戏子进程注册
# =========================
_game_procs: dict[str, subprocess.Popen] = {}
_game_ports: dict[str, int] = {}
_lock = threading.Lock()


def terminate_all_games() -> None:
    with _lock:
        for script, proc in list(_game_procs.items()):
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        _game_procs.clear()
        _game_ports.clear()


atexit.register(terminate_all_games)


def streamlit_runner_port(script: str, work_dir: str) -> int:
    """获取/启动某脚本对应的 streamlit 子进程端口。"""
    with _lock:
        proc = _game_procs.get(script)
        if proc is not None and proc.poll() is None:
            return _game_ports[script]
        port = find_free_port()
        base = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
        cmd = base + [
            WORKER_FLAG, "run", script,
            "--server.port=" + str(port),
            "--server.address=127.0.0.1",
            "--server.headless=true",
            "--server.runOnSave=false",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
            "--client.toolbarMode=minimal",
            "--global.developmentMode=false",
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        # 把 worker 输出落到日志，便于排查（DEVNULL 时崩溃不可见）
        log_dir = os.path.join(os.path.dirname(work_dir), "logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"{script[:-3]}_{port}.log")
        except Exception:
            log_path = os.devnull
        try:
            log_fp = open(log_path, "w", encoding="utf-8", buffering=1) if isinstance(log_path, str) and log_path != os.devnull else subprocess.DEVNULL
            proc = subprocess.Popen(
                cmd, cwd=work_dir, env=env,
                stdout=log_fp, stderr=subprocess.STDOUT,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        except Exception as e:
            raise RuntimeError(f"启动 streamlit 失败：{e}")
        _game_procs[script] = proc
        _game_ports[script] = port
        return port


# =========================
# HTTP 服务
# =========================
class LauncherHandler(BaseHTTPRequestHandler):
    # 关闭默认访问日志
    def log_message(self, fmt, *args):  # noqa: D401
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        if self.path in ("", "/"):
            path = frontend_html_path()
            try:
                with open(path, "rb") as f:
                    data = f.read()
                self._send(200, data, "text/html")
            except FileNotFoundError:
                self._send(404, b'{"error":"frontend missing"}', "application/json")
            return
        if self.path == "/api/ping":
            self._send(200, b'{"ok":true}', "application/json")
            return
        if self.path.startswith("/api/health"):
                # query: ?script=app_03_mini.py
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            script = (qs.get("script", [""])[0] or "").strip()
            info = {"ok": True, "running": [], "logs_dir": ""}
            with _lock:
                for s, port in _game_ports.items():
                    alive = _game_procs.get(s) is not None and _game_procs[s].poll() is None
                    info["running"].append({"script": s, "port": port, "alive": alive})
            logs_dir = os.path.join(os.path.dirname(self.server.work_dir), "logs")  # type: ignore[attr-defined]
            info["logs_dir"] = logs_dir
            tail = ""
            if script:
                base = script[:-3] if script.endswith(".py") else script
                # 找最新匹配日志
                if os.path.isdir(logs_dir):
                    matches = [f for f in os.listdir(logs_dir) if f.startswith(base + "_")]
                    if matches:
                        lp = os.path.join(logs_dir, sorted(matches)[-1])
                        try:
                            with open(lp, "r", encoding="utf-8", errors="ignore") as f:
                                tail = "".join(f.readlines()[-12:])
                        except Exception:
                            tail = ""
            info["tail"] = tail
            self._send(200, json.dumps(info, ensure_ascii=False).encode("utf-8"), "application/json")
            return
        self._send(404, b'{"error":"not found"}', "application/json")

    def do_POST(self):
        if self.path != "/api/launch":
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._send(400, b'{"ok":false,"error":"bad json"}', "application/json")
            return

        script = (payload.get("script") or "").strip()
        api_key = (payload.get("api_key") or "").strip()
        api_url = (payload.get("api_url") or "").strip()
        model = (payload.get("model") or "").strip()
        provider = (payload.get("provider") or "").strip().lower()

        if not script:
            self._send(400, b'{"ok":false,"error":"missing script"}', "application/json")
            return
        if not api_key:
            self._send(400, b'{"ok":false,"error":"missing api key"}', "application/json")
            return

        # 限制仅允许预定义脚本，防止任意命令执行
        allowed = {"app.py", "app_03_mini.py", "app_03_ming.py"}
        if os.path.basename(script) not in allowed:
            self._send(400, b'{"ok":false,"error":"script not allowed"}', "application/json")
            return
        script = os.path.basename(script)

        # 注入环境变量供 streamlit app 内 config/llm_client 读取
        os.environ["LLM_API_KEY"] = api_key
        if provider == "zhipu" or provider == "":
            os.environ["ZHIPU_API_KEY"] = api_key
        if api_url:
            os.environ["LLM_API_URL"] = api_url
        if model:
            os.environ["LLM_MODEL"] = model

        try:
            port = streamlit_runner_port(script, self.server.work_dir)  # type: ignore[attr-defined]
        except Exception as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return

        url = f"http://127.0.0.1:{port}/"
        # 后台等待 streamlit 就绪后开浏览器新标签
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
        body = json.dumps({"ok": True, "port": port, "url": url}).encode("utf-8")
        self._send(200, body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


def _open_when_ready(url: str, timeout: float = 30.0) -> None:
    """轮询直到 streamlit 端口可连且游戏根页可拉取（无 ModuleNotFoundError），再开浏览器。

    去假阳性关键：仅端口可连不足以证明脚本无 import 崩溃，
    必须实际拉根 URL 并断言不含 Uncaught app execution / ModuleNotFoundError。
    """
    port = int(url.rsplit(":", 1)[-1].rstrip("/"))
    deadline = time.time() + timeout
    # 阶段1：端口可连
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                break
        except OSError:
            time.sleep(0.4)
    # 阶段2：根页 HTTP 200 且无 import 崩溃标记（streamlit 脚本异常会在首页内嵌错误段）
    healthy = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                body = resp.read(65536).decode("utf-8", errors="ignore")
            if resp.status == 200:
                if "ModuleNotFoundError" in body or "Uncaught app execution" in body:
                    sys.stderr.write(f"[launcher] streamlit script error detected at {url}\n")
                    time.sleep(1.0)
                    continue
                healthy = True
                break
        except Exception:
            time.sleep(0.5)
    if not healthy:
        sys.stderr.write(f"[launcher] streamlit not healthy after {timeout}s: {url}\n")
        # 仍打开，方便用户看错页/日志，但 stderr 已留痕
    try:
        webbrowser.open(url)
    except Exception:
        pass


def serve(work_dir: str, http_port: int) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", http_port), LauncherHandler)
    httpd.work_dir = work_dir  # type: ignore[attr-defined]
    httpd.serve_forever()


# =========================
# Worker 派遣：argv[1]==WORKER_FLAG 时直接跑 streamlit
# =========================
def run_streamlit_worker() -> int:
    try:
        from streamlit.web import cli as stcli
    except Exception as e:
        sys.stderr.write(f"[streamlit-worker] import streamlit failed: {e}\n")
        return 2
    # streamlit 期望 argv: ["streamlit", "run", <script>, opts...]
    sys.argv = ["streamlit"] + sys.argv[2:]
    try:
        stcli.main()
    except SystemExit as e:
        return int(getattr(e, "code", 0) or 0)
    return 0


# =========================
# 主入口
# =========================
def main() -> int:
    # 派遣子进程：执行 streamlit
    if len(sys.argv) >= 2 and sys.argv[1] == WORKER_FLAG:
        return run_streamlit_worker()

    try:
        work_dir = ensure_runtime_files()
    except Exception:
        traceback.print_exc()
        return 3

    http_port = find_free_port(start=8750)
    base_url = f"http://127.0.0.1:{http_port}/"

    threading.Thread(target=serve, args=(work_dir, http_port), daemon=True).start()

    # 等服务起来再开浏览器
    time.sleep(0.3)
    try:
        webbrowser.open(base_url)
    except Exception:
        pass

    print(f"[{APP_TITLE}] 启动器已就绪：{base_url}\n关闭本窗口即可退出。")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        terminate_all_games()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())