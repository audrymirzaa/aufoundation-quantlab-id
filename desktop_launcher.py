from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP_NAME = "QuantLab"
DEFAULT_PORT = 8501
CREATE_NO_WINDOW = 0x08000000


def show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, APP_NAME, 0x10)
    except Exception:
        print(message)


def find_base() -> Path:
    candidates = [Path(sys.executable).resolve().parent, Path(__file__).resolve().parent, Path.cwd()]
    for candidate in candidates:
        if (candidate / "app.py").exists():
            return candidate
        if (candidate.parent / "app.py").exists():
            return candidate.parent
    return candidates[0]


def port_free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wsl_path(base: Path) -> str | None:
    text = str(base)
    if len(text) >= 2 and text[1] == ":":
        return "/mnt/" + text[0].lower() + text[2:].replace("\\", "/")
    return None


def server_command(base: Path, port: int) -> list[str]:
    win_python = base / ".venv-win" / "Scripts" / "python.exe"
    if win_python.exists():
        return [
            str(win_python),
            "-m",
            "streamlit",
            "run",
            str(base / "app.py"),
            "--server.headless",
            "true",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(port),
        ]
    wsl_dir = wsl_path(base)
    if os.name == "nt" and wsl_dir and (base / ".venv" / "bin" / "python").exists():
        command = (
            f"cd '{wsl_dir}' && exec .venv/bin/python -m streamlit run app.py "
            f"--server.headless true --server.address 127.0.0.1 --server.port {port}"
        )
        return ["wsl", "bash", "-lc", command]
    python = shutil.which("python") or shutil.which("python3")
    if python:
        return [
            python,
            "-m",
            "streamlit",
            "run",
            str(base / "app.py"),
            "--server.headless",
            "true",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(port),
        ]
    raise RuntimeError("Python belum siap. Jalankan build_exe.bat terlebih dahulu.")


def wait_http(url: str, timeout: float = 120.0, splash=None) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except Exception:
            pass
        if splash is not None:
            try:
                splash.update()
            except Exception:
                pass
        time.sleep(1)
    return False


def splash_window():
    try:
        import tkinter as tk

        root = tk.Tk()
        root.title(APP_NAME)
        root.geometry("360x130")
        root.resizable(False, False)
        root.configure(bg="#ffffff")
        tk.Label(root, text=APP_NAME, font=("Georgia", 16, "bold"), bg="#ffffff", fg="#101828").pack(pady=(18, 4))
        tk.Label(root, text="Menyiapkan server dan data...", font=("Segoe UI", 9), bg="#ffffff", fg="#475467").pack()
        root.update()
        return root
    except Exception:
        return None


def open_fallback(url: str) -> None:
    edge = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    try:
        if edge.exists():
            subprocess.Popen([str(edge), f"--app={url}"])
        else:
            import webbrowser

            webbrowser.open(url)
    except Exception:
        import webbrowser

        webbrowser.open(url)


def main() -> int:
    base = find_base()
    if not (base / "app.py").exists():
        show_error("app.py tidak ditemukan di folder QuantLab.")
        return 1
    port = DEFAULT_PORT
    url = f"http://127.0.0.1:{port}"
    existing = False
    try:
        with urllib.request.urlopen(url, timeout=1):
            existing = True
    except Exception:
        existing = False
    process = None
    log = None
    if not existing:
        if not port_free(port):
            port = free_port()
        url = f"http://127.0.0.1:{port}"
        log = open(base / "quantlab.log", "a", encoding="utf-8", errors="replace")
        env = os.environ.copy()
        env.update(
            {
                "STREAMLIT_SERVER_HEADLESS": "true",
                "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
                "STREAMLIT_SERVER_FILE_WATCHER_TYPE": "none",
            }
        )
        try:
            process = subprocess.Popen(
                server_command(base, port),
                cwd=str(base),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:
            if log:
                log.close()
            show_error(str(exc))
            return 1
        splash = splash_window()
        if not wait_http(url, 120, splash):
            process.terminate()
            if splash is not None:
                splash.destroy()
            if log:
                log.close()
            show_error("Server QuantLab tidak siap. Baca quantlab.log di folder QuantLab.")
            return 1
        if splash is not None:
            splash.destroy()
    try:
        import webview

        webview.create_window(APP_NAME, url, width=1440, height=920, min_size=(1000, 700))
        webview.start()
    except Exception:
        open_fallback(url)
        try:
            import tkinter as tk

            root = tk.Tk()
            root.title(APP_NAME)
            root.geometry("360x120")
            tk.Label(
                root,
                text="QuantLab berjalan. Tutup jendela ini untuk menghentikan server.",
                wraplength=320,
            ).pack(pady=24)
            root.mainloop()
        except Exception:
            if process is not None:
                process.wait()
    finally:
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass
        if log is not None:
            try:
                log.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
