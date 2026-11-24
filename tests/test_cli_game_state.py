from __future__ import annotations

from datetime import UTC, datetime, timedelta

from btd6.cli import main
from btd6.game_state import fake_game_state, save_game_state


def state_arguments(tmp_path):
    return ["--state-file", str(tmp_path / "game_state.json")]


def test_main_fake_state_then_game_state(tmp_path, capsys):
    fake_exit = main(
        [
            *state_arguments(tmp_path),
            "fake-state",
            "--round",
            "40",
            "--money",
            "5000",
            "--tower",
            "Dart Monkey:0-2-3",
        ]
    )
    capsys.readouterr()
    show_exit = main([*state_arguments(tmp_path), "game-state"])
    output = capsys.readouterr().out
    assert fake_exit == 0
    assert show_exit == 0
    assert "Round 40" in output
    assert "Money $5,000" in output
    assert "Difficulty medium" in output
    assert "Dart Monkey 0-2-3" in output


def test_main_game_state_missing(tmp_path, capsys):
    path = tmp_path / "game_state.json"
    exit_code = main([*state_arguments(tmp_path), "game-state"])
    assert exit_code == 1
    assert capsys.readouterr().err.strip() == (
        f"No game state at {path}. Start the game with the mod and "
        '"python -m btd6 serve", or run "python -m btd6 fake-state".'
    )


def test_main_game_state_stale(tmp_path, capsys):
    stale_time = datetime.now(UTC) - timedelta(seconds=60)
    path = tmp_path / "game_state.json"
    save_game_state(path, fake_game_state(40, 5000), received_at=stale_time)
    exit_code = main([*state_arguments(tmp_path), "game-state", "--max-age", "30"])
    assert exit_code == 1
    assert capsys.readouterr().err.startswith("Game state is stale")


def test_main_fake_state_malformed_tower(tmp_path, capsys):
    exit_code = main(
        [
            *state_arguments(tmp_path),
            "fake-state",
            "--round",
            "40",
            "--money",
            "5000",
            "--tower",
            "Dart Monkey",
        ]
    )
    assert exit_code == 2
    assert 'Tower must be NAME:X-Y-Z, got "Dart Monkey"' in capsys.readouterr().err


def test_main_fake_state_unknown_tower(tmp_path, capsys):
    exit_code = main(
        [
            *state_arguments(tmp_path),
            "fake-state",
            "--round",
            "40",
            "--money",
            "5000",
            "--tower",
            "Banana Farm:2-0-0",
        ]
    )
    assert exit_code == 2
    assert 'Unknown tower "Banana Farm"' in capsys.readouterr().err
