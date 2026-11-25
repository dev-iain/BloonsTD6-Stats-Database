from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import requests

API_KEY_VARIABLE = "GEMINI_API_KEY"
MODEL_VARIABLE = "BTD6_AGENT_MODEL"
BASE_URL_VARIABLE = "BTD6_AGENT_BASE_URL"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
REQUEST_TIMEOUT_SECONDS = 30
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRY_DELAYS_SECONDS = (2.0, 5.0)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
KEY_FILE_NAME = "gemini_api_key.txt"
API_KEY_FILES = (PROJECT_ROOT / ".env", PROJECT_ROOT / KEY_FILE_NAME)
MISSING_KEY_MESSAGE = (
    f"{API_KEY_VARIABLE} is not set. Get a free key at https://aistudio.google.com/apikey "
    f"and paste it into {KEY_FILE_NAME} in the project folder (or export {API_KEY_VARIABLE})."
)
KEY_FILE_TEMPLATE = (
    "# Paste your free Gemini API key below on its own line.\n"
    "# Get one at https://aistudio.google.com/apikey\n"
)


class AgentError(Exception):
    """The agent could not produce an answer."""


class MissingApiKeyError(AgentError):
    """No API key in the environment."""


class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.session = session if session is not None else requests.Session()
        self.sleep = sleep if sleep is not None else time.sleep

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        cause = ""
        for delay in (*RETRY_DELAYS_SECONDS, None):
            response, cause = self.post_once(messages, tools)
            if response is not None:
                self.raise_for_status(response)
                return response.json()["choices"][0]["message"]
            if delay is not None:
                self.sleep(delay)
        raise AgentError(
            f"{self.model} is busy or unreachable ({cause}) after "
            f"{len(RETRY_DELAYS_SECONDS) + 1} attempts. Try again in a minute, "
            f"or set {MODEL_VARIABLE} to another model."
        )

    def post_once(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[requests.Response | None, str]:
        try:
            response = self.session.post(
                f"{self.base_url}chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "tools": tools},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.Timeout:
            return None, "timed out"
        except requests.ConnectionError:
            return None, "connection error"
        except requests.RequestException as error:
            raise AgentError(f"Request to {self.model} failed: {error}") from error
        if response.status_code in RETRY_STATUSES:
            return None, f"HTTP {response.status_code}"
        return response, ""

    def raise_for_status(self, response: requests.Response) -> None:
        if response.status_code in (401, 403):
            raise AgentError(
                f"HTTP {response.status_code}: the provider rejected the API key. "
                f"Check {API_KEY_VARIABLE}."
            )
        if not response.ok:
            raise AgentError(f"HTTP {response.status_code} from provider: {response.text[:200]}")


def strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1].strip()
    return text


def key_from_line(line: str) -> str:
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    line = line.removeprefix("export ").strip()
    name, separator, value = line.partition("=")
    if not separator:
        return strip_quotes(line)
    if name.strip() != API_KEY_VARIABLE:
        return ""
    return strip_quotes(value)


def read_key_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        key = key_from_line(line)
        if key:
            return key
    return ""


def find_api_key(environ: Mapping[str, str], key_files: Sequence[Path] = ()) -> str:
    api_key = environ.get(API_KEY_VARIABLE, "").strip()
    if api_key:
        return api_key
    return next((key for key in map(read_key_file, key_files) if key), "")


def write_key_file_template(path: Path) -> bool:
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(KEY_FILE_TEMPLATE)
    except OSError:
        return False
    return True


def client_from_environment(
    environ: Mapping[str, str], key_files: Sequence[Path] = ()
) -> OpenAICompatibleClient:
    api_key = find_api_key(environ, key_files)
    if not api_key:
        raise MissingApiKeyError(MISSING_KEY_MESSAGE)
    return OpenAICompatibleClient(
        api_key,
        environ.get(MODEL_VARIABLE, DEFAULT_MODEL),
        environ.get(BASE_URL_VARIABLE, DEFAULT_BASE_URL),
    )
