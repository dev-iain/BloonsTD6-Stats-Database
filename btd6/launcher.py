from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import requests

STEAM_GAME_URI = "steam://rungameid/960090"
WILDCARD_HOSTS = ("0.0.0.0", "::", "")
LOCAL_HOST = "127.0.0.1"
READY_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.1
STOP_TIMEOUT_SECONDS = 10


def reachable_host(host: str) -> str:
    return LOCAL_HOST if host in WILDCARD_HOSTS else host


def browser_url(host: str, port: int) -> str:
    return f"http://{reachable_host(host)}:{port}"


def open_uri(uri: str) -> None:
    if sys.platform == "win32":
        os.startfile(uri)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", uri])
    else:
        subprocess.Popen(["xdg-open", uri])


def launch_game() -> None:
    open_uri(STEAM_GAME_URI)


def wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((reachable_host(host), port), timeout=0.5):
                return True
        except OSError:
            time.sleep(POLL_INTERVAL_SECONDS)
    return False


def open_when_listening(url: str, host: str, port: int) -> None:
    if wait_for_port(host, port, READY_TIMEOUT_SECONDS):
        webbrowser.open(url)


def open_browser_when_ready(url: str, host: str, port: int) -> threading.Thread:
    thread = threading.Thread(target=open_when_listening, args=(url, host, port), daemon=True)
    thread.start()
    return thread


def port_in_use(host: str, port: int) -> bool:
    try:
        with socket.create_connection((reachable_host(host), port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_for_port_free(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if not port_in_use(host, port):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL_SECONDS)


def running_advisor_pid(host: str, port: int) -> int | None:
    url = f"http://{reachable_host(host)}:{port}/api/health"
    try:
        payload = requests.get(url, timeout=2).json()
    except requests.RequestException, ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("app") != "btd6":
        return None
    pid = payload.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int):
        return None
    return pid


def stop_process(pid: int) -> None:
    if pid == os.getpid():
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def replace_running_advisor(host: str, port: int) -> str | None:
    if not port_in_use(host, port):
        return None
    pid = running_advisor_pid(host, port)
    if pid is None:
        return (
            f"Port {port} is already in use. If an older BTD6 advisor is running, "
            "close its window (or press Ctrl+C in it) and run the start script again; "
            "otherwise use --port N."
        )
    print(f"Stopping the advisor that is already running (pid {pid})...")
    stop_process(pid)
    if wait_for_port_free(host, port, STOP_TIMEOUT_SECONDS):
        return None
    return (
        f"Could not stop the advisor on port {port} (pid {pid}). "
        "Close its window and run the start script again."
    )
