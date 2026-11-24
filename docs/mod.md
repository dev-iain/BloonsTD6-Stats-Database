# Game-state mod (`mod/`)

The mod is the producer of the live game state contract in [game-state.md](game-state.md). Install and build steps are in [mod/README.md](../mod/README.md).

## Decisions

| Decision | Reason |
|---|---|
| Same repo, `mod/` folder | One deliverable, and the contract fixture (`tests/fixtures/game_state/valid.json`) is read by both the Python tests and the C# tests. `git subtree split` can move it out later |
| Outbound HTTP POST from the mod to `serve` | Works the same on Windows and under Proton (Wine uses the host network stack); no `HttpListener` inside Wine |
| All interpretation in Python | Name mapping, validation, difficulty mapping and staleness are tested with TDD/ISP/mutmut in `btd6/game_state.py`. The mod sends raw game ids, tiers, difficulty and mode |
| Game-independent code in `GameStateReporter.Core` | It is compiled into the mod DLL, and also built on its own so `dotnet test` runs without BTD6 installed |
| Read only | No buying or placing; offline/solo play only |

## What the mod reads

| Contract key | Source (main thread, `InGame.instance`) |
|---|---|
| `round` | `bridge.GetCurrentRound() + 1` (the game counts from 0) |
| `cash` | `GetCash()` (Mod Helper extension) |
| `lives` | `GetHealth()` (Mod Helper extension) |
| `difficulty` | `SelectedDifficulty` (`Easy`, `Medium`, `Hard`) |
| `mode` | `SelectedMode` (`Standard`, `Impoppable`, `Clicks` for CHIMPS, ...) |
| `map` | `SelectedMap` |
| `towers` | `GetTowers()`: `towerModel.baseId` and `towerModel.tiers`. Sub-towers (`isSubTower`, e.g. sentries) are skipped. Tiers are clamped to three values from 0 to 5 |

Outside a match (`InGame.instance` or its `bridge` is null) nothing is sent, and the send policy is reset so the next match is sent at once. An exception while reading is logged (rate-limited) and treated the same way.

## When it sends (`SendPolicy`)

- The state is read at most once per second (`ReadInterval`), or at once on the next frame after a round starts or a tower is created, upgraded or sold (Mod Helper hooks mark the policy dirty).
- A read snapshot is posted if its JSON differs from the last one sent, or if 5 seconds (`HeartbeatInterval`) have passed. The heartbeat keeps the stored state younger than the 30-second staleness limit while the game is idle.
- At most one POST is in flight (1 s timeout). A snapshot that could not be posted because one was still running is not recorded as sent, so it goes out on the next read.
- Failures (server down, HTTP 422) are logged at most once a minute (`RateLimitedLog`) and never thrown into the game loop.

## Tests

`mod/GameStateReporter.Tests` (xunit): the serialised snapshot equals the shared fixture (`JsonNode.DeepEquals`) and keeps the contract's key order; cash and lives are never negative or non-finite; tier clamping; round conversion; read throttling, dirty reads, change detection, heartbeat and reset; the log rate limit.

The game-facing layer (`Main.cs`, `GameReader.cs`, `StatePoster.cs`) needs the game's Il2Cpp assemblies to build, so it is checked by hand: build, play a round with `serve` running, and watch `game-state` and the Recommend tab update; stop the server and check the MelonLoader console shows one warning a minute and the game keeps running.
