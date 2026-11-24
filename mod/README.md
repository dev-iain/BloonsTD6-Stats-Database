# GameStateReporter (BTD6 mod)

A MelonLoader + BTD Mod Helper mod that posts the live game (round, cash, lives, difficulty, mode, map and placed towers) to `python -m btd6 serve`. The Recommend tab's **Use live game** toggle, `recommend --live` and `agent --live` then use it instead of typed-in values. The JSON contract is [docs/game-state.md](../docs/game-state.md) and the design is in [docs/mod.md](../docs/mod.md).

> **Offline/solo play only.** Ninja Kiwi can flag accounts that play modded games online. This mod only reads state; it never buys, places or upgrades anything.

## Layout

| Path | Contents |
|---|---|
| `GameStateReporter/` | The mod: `Main.cs` (settings, update loop, hooks), `GameReader.cs` (reads `InGame`), `StatePoster.cs` (HTTP POST) |
| `GameStateReporter.Core/` | Game-independent code compiled into the mod: the snapshot DTO and JSON, `SendPolicy` (throttle, heartbeat), `RateLimitedLog` |
| `GameStateReporter.Tests/` | xunit tests for Core. They also check the JSON against `tests/fixtures/game_state/valid.json`, the fixture the Python tests use |
| `Directory.Build.props` | Finds the game folder; override with a gitignored `Directory.Build.props.user` |

## 1. Install MelonLoader and BTD Mod Helper

### Windows

1. Install [MelonLoader](https://github.com/LavaGang/MelonLoader/releases) with its installer and point it at `BloonsTD6.exe` (Steam: right-click BTD6 → Manage → Browse local files).
2. Download `Btd6ModHelper.dll` from the [BTD Mod Helper releases](https://github.com/gurrenm3/BTD-Mod-Helper/releases) into the game's `Mods/` folder.
3. Start BTD6 once and quit. MelonLoader generates `MelonLoader/Il2CppAssemblies/`, which the build needs.

### Linux (Steam Proton)

1. Extract the MelonLoader x64 release zip into the game folder, `~/.local/share/Steam/steamapps/common/BloonsTD6`, so `version.dll` and `MelonLoader/` sit next to `BloonsTD6.exe`. (The MelonLoader installer also works under Linux.)
2. In Steam, set BTD6's launch options to:

   ```text
   WINEDLLOVERRIDES="version=n,b" %command%
   ```

   Without it, Wine uses its own `version.dll` and MelonLoader never loads.
3. Put `Btd6ModHelper.dll` in `Mods/`, start BTD6 once and quit, as on Windows.

## 2. Build

Needs the .NET 6 SDK or later.

```bash
dotnet build mod/GameStateReporter
```

The build references the game's MelonLoader, Il2Cpp and Mod Helper DLLs and copies `GameStateReporter.dll` into the game's `Mods/` folder. It looks for the game at the default Steam path (`C:/Program Files (x86)/Steam/steamapps/common/BloonsTD6` on Windows, `~/.local/share/Steam/steamapps/common/BloonsTD6` elsewhere). For another location, create `mod/Directory.Build.props.user` (gitignored):

```xml
<Project>
  <PropertyGroup>
    <BloonsTD6>/mnt/games/SteamLibrary/steamapps/common/BloonsTD6</BloonsTD6>
  </PropertyGroup>
</Project>
```

or pass `-p:BloonsTD6=...`. If MelonLoader or Mod Helper is missing, the build stops with a message saying which.

Tests for the game-independent code need no game:

```bash
dotnet test mod/GameStateReporter.Tests
```

## 3. Run

1. Start the server: `uv run python -m btd6 serve`.
2. Start BTD6 and play a game. Within a second the server has the state:

   ```bash
   uv run python -m btd6 game-state
   curl http://127.0.0.1:8000/api/game-state
   ```

3. Open `http://127.0.0.1:8000`, go to **Recommend** and tick **Use live game**, or run `uv run python -m btd6 recommend --live`.

### Settings

In BTD6: Mods → GameStateReporter → settings.

| Setting | Default | Meaning |
|---|---|---|
| Enabled | on | Send the state |
| Server Url | `http://127.0.0.1:8000/api/game-state` | Where to POST. Use another PC's address (and `serve --host 0.0.0.0` there) to report across a LAN |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| No MelonLoader console when the game starts (Linux) | The `WINEDLLOVERRIDES` launch option is missing |
| `could not reach http://127.0.0.1:8000/...` in the MelonLoader console | The server is not running. The mod logs this at most once a minute and keeps trying; the game is not affected |
| `... answered 422: Unknown difficulty` | The mode has no Easy/Medium/Hard difficulty (e.g. some event modes). The state is not stored |
| `game-state` says the state is stale | No post in the last 30 s: the game is in the main menu, closed, or the mod is disabled |
| A tower shows `(not in the database)` | Only the ten towers in `KNOWN_TOWERS` are loaded; others (heroes, farms, ...) are kept with `known: false` |
| Build error about `Il2CppAssemblies` | Start the game once with MelonLoader installed, or set `BloonsTD6` |
