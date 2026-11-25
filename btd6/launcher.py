from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

STEAM_GAME_URI = "steam://rungameid/960090"
WILDCARD_HOSTS = ("0.0.0.0", "::", "")
LOCAL_HOST = "127.0.0.1"
READY_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.1


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
