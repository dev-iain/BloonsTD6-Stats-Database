from __future__ import annotations

from pathlib import Path

import pytest

from btd6.agent import client as client_module
from btd6.agent.client import (
    API_KEY_FILES,
    KEY_FILE_NAME,
    MISSING_KEY_MESSAGE,
    PROJECT_ROOT,
    MissingApiKeyError,
    OpenAICompatibleClient,
    client_from_environment,
    find_api_key,
    read_key_file,
    write_key_file_template,
)

SIGNUP_URL = "https://aistudio.google.com/apikey"


def write_text(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_constants() -> None:
    assert KEY_FILE_NAME == "gemini_api_key.txt"
    assert PROJECT_ROOT == Path(client_module.__file__).resolve().parents[2]
    assert (PROJECT_ROOT / "pyproject.toml").exists()
    assert API_KEY_FILES == (PROJECT_ROOT / ".env", PROJECT_ROOT / KEY_FILE_NAME)
    assert MISSING_KEY_MESSAGE == (
        "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
        "and paste it into gemini_api_key.txt in the project folder (or export GEMINI_API_KEY)."
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('OTHER=1\nGEMINI_API_KEY="abc"\n', "abc"),
        ("# paste below\n\n  abc  \n", "abc"),
        ("export GEMINI_API_KEY=abc\n", "abc"),
        ("# only\n# comments\n", ""),
        ("", ""),
        ("GEMINI_API_KEY=\nGEMINI_API_KEY=later\n", "later"),
        ("GEMINI_API_KEY=\n", ""),
        ("OTHER=1\n", ""),
        ("GEMINI_API_KEY='single'\n", "single"),
        ("  GEMINI_API_KEY = spaced  \n", "spaced"),
        ('"quoted-bare"\n', "quoted-bare"),
        ("OTHER=nope\nplainkey\n", "plainkey"),
        ("GEMINI_API_KEY=a=b\n", "a=b"),
        ("  # indented comment\nabc\n", "abc"),
        ('GEMINI_API_KEY="  padded  "\n', "padded"),
        ("GEMINI_API_KEY=first\nGEMINI_API_KEY=second\n", "first"),
        ("export OTHER=1\nexport GEMINI_API_KEY='x'\n", "x"),
    ],
)
def test_read_key_file(tmp_path: Path, text: str, expected: str) -> None:
    assert read_key_file(write_text(tmp_path, "key.txt", text)) == expected


def test_read_key_file_missing(tmp_path: Path) -> None:
    assert read_key_file(tmp_path / "absent.txt") == ""


def test_find_api_key_environment_wins(tmp_path: Path) -> None:
    key_file = write_text(tmp_path, "key.txt", "file-key")

    assert find_api_key({"GEMINI_API_KEY": " env-key "}, (key_file,)) == "env-key"


@pytest.mark.parametrize("environ", [{}, {"GEMINI_API_KEY": ""}, {"GEMINI_API_KEY": "  "}])
def test_find_api_key_falls_back_to_files(tmp_path: Path, environ: dict[str, str]) -> None:
    key_file = write_text(tmp_path, "key.txt", "file-key")

    assert find_api_key(environ, (key_file,)) == "file-key"


def test_find_api_key_first_file_wins(tmp_path: Path) -> None:
    dotenv = write_text(tmp_path, ".env", "GEMINI_API_KEY=env-file\n")
    plain = write_text(tmp_path, "key.txt", "txt-file")

    assert find_api_key({}, (dotenv, plain)) == "env-file"


def test_find_api_key_skips_empty_and_missing_files(tmp_path: Path) -> None:
    comments = write_text(tmp_path, ".env", "# nothing\n")
    plain = write_text(tmp_path, "key.txt", "txt-file")

    assert find_api_key({}, (tmp_path / "absent", comments, plain)) == "txt-file"


def test_find_api_key_nothing_found(tmp_path: Path) -> None:
    assert find_api_key({}, ()) == ""
    assert find_api_key({}, (tmp_path / "absent",)) == ""


def test_client_from_environment_reads_key_files(tmp_path: Path) -> None:
    key_file = write_text(tmp_path, "key.txt", "file-key")

    client = client_from_environment({}, (key_file,))

    assert isinstance(client, OpenAICompatibleClient)
    assert client.api_key == "file-key"


def test_client_from_environment_without_files_ignores_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / KEY_FILE_NAME).write_text("file-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MissingApiKeyError) as caught:
        client_from_environment({})

    assert str(caught.value) == MISSING_KEY_MESSAGE


def test_client_from_environment_missing_everywhere_uses_new_message(tmp_path: Path) -> None:
    with pytest.raises(MissingApiKeyError) as caught:
        client_from_environment({}, (tmp_path / "absent",))

    assert str(caught.value) == MISSING_KEY_MESSAGE


def test_write_key_file_template_creates_inert_file(tmp_path: Path) -> None:
    path = tmp_path / KEY_FILE_NAME

    assert write_key_file_template(path) is True

    text = path.read_text(encoding="utf-8")
    assert SIGNUP_URL in text
    assert all(not line.strip() or line.lstrip().startswith("#") for line in text.splitlines())
    assert read_key_file(path) == ""


def test_write_key_file_template_never_overwrites(tmp_path: Path) -> None:
    path = write_text(tmp_path, KEY_FILE_NAME, "my-secret-key\n")

    assert write_key_file_template(path) is False
    assert path.read_text(encoding="utf-8") == "my-secret-key\n"


def test_gitignore_lists_key_file(repo_root: Path) -> None:
    lines = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert KEY_FILE_NAME in lines
