using System;
using System.Text.Json;

namespace GameStateReporter;

public static class SnapshotJson
{
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = false };

    /// <summary>Serialises to the contract shape. Cash and lives must be finite and not negative.</summary>
    public static string Serialize(GameSnapshot snapshot)
    {
        var cleaned = new GameSnapshot
        {
            Version = snapshot.Version,
            Round = snapshot.Round,
            Cash = NonNegative(snapshot.Cash),
            Lives = NonNegative(snapshot.Lives),
            Difficulty = snapshot.Difficulty,
            Mode = snapshot.Mode,
            Map = snapshot.Map,
            Towers = snapshot.Towers,
        };
        return JsonSerializer.Serialize(cleaned, Options);
    }

    private static double NonNegative(double value) =>
        double.IsFinite(value) ? Math.Max(value, 0) : 0;
}
