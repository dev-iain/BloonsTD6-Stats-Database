using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace GameStateReporter;

/// <summary>One placed tower in the version 1 game state contract (docs/game-state.md).</summary>
public sealed class TowerSnapshot
{
    public const int MaxTier = 5;

    public TowerSnapshot(string baseId, IReadOnlyList<int> tiers)
    {
        BaseId = baseId;
        Tiers = ClampTiers(tiers);
    }

    [JsonPropertyName("base_id")]
    public string BaseId { get; }

    [JsonPropertyName("tiers")]
    public int[] Tiers { get; }

    /// <summary>Returns exactly three tiers, each from 0 to 5. Paragons and odd models can report more.</summary>
    public static int[] ClampTiers(IReadOnlyList<int> tiers)
    {
        var clamped = new int[3];
        for (var position = 0; position < clamped.Length && position < tiers.Count; position++)
        {
            clamped[position] = Math.Clamp(tiers[position], 0, MaxTier);
        }
        return clamped;
    }
}

/// <summary>The payload the mod posts to POST /api/game-state.</summary>
public sealed class GameSnapshot
{
    public const int ContractVersion = 1;

    [JsonPropertyName("version")]
    public int Version { get; init; } = ContractVersion;

    /// <summary>One-based round: the game's zero-based current round plus one.</summary>
    [JsonPropertyName("round")]
    public int Round { get; init; }

    [JsonPropertyName("cash")]
    public double Cash { get; init; }

    [JsonPropertyName("lives")]
    public double Lives { get; init; }

    [JsonPropertyName("difficulty")]
    public string Difficulty { get; init; } = "";

    [JsonPropertyName("mode")]
    public string Mode { get; init; } = "";

    [JsonPropertyName("map")]
    public string Map { get; init; } = "";

    [JsonPropertyName("towers")]
    public IReadOnlyList<TowerSnapshot> Towers { get; init; } = Array.Empty<TowerSnapshot>();

    public static int RoundFromGame(int zeroBasedRound) => Math.Max(zeroBasedRound, 0) + 1;
}
