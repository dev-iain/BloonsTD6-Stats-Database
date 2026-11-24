using System;
using System.IO;
using System.Text.Json.Nodes;
using GameStateReporter;
using Xunit;

namespace GameStateReporter.Tests;

public class SnapshotJsonTests
{
    private static readonly string FixturePath =
        Path.Combine(AppContext.BaseDirectory, "fixtures", "valid.json");

    private static GameSnapshot ValidSnapshot(double cash = 5123.7, double lives = 150) => new()
    {
        Round = 40,
        Cash = cash,
        Lives = lives,
        Difficulty = "Medium",
        Mode = "Standard",
        Map = "Monkey Meadow",
        Towers = new[]
        {
            new TowerSnapshot("DartMonkey", new[] { 0, 2, 3 }),
            new TowerSnapshot("BananaFarm", new[] { 2, 0, 0 }),
        },
    };

    private static JsonNode Parse(string json) => JsonNode.Parse(json)!;

    [Fact]
    public void TestSerializeMatchesSharedFixture()
    {
        var expected = Parse(File.ReadAllText(FixturePath));

        var actual = Parse(SnapshotJson.Serialize(ValidSnapshot()));

        Assert.True(JsonNode.DeepEquals(expected, actual), actual.ToJsonString());
    }

    [Fact]
    public void TestSerializeKeyOrderFollowsContract()
    {
        var keys = Parse(SnapshotJson.Serialize(ValidSnapshot())).AsObject();

        Assert.Equal(
            new[] { "version", "round", "cash", "lives", "difficulty", "mode", "map", "towers" },
            System.Linq.Enumerable.ToArray(System.Linq.Enumerable.Select(keys, pair => pair.Key)));
    }

    [Fact]
    public void TestSerializeNoTowers()
    {
        var snapshot = new GameSnapshot { Round = 1, Difficulty = "Easy", Mode = "Standard" };

        var towers = Parse(SnapshotJson.Serialize(snapshot))["towers"]!.AsArray();

        Assert.Empty(towers);
    }

    [Theory]
    [InlineData(-5.0, 0.0)]
    [InlineData(double.NaN, 0.0)]
    [InlineData(double.PositiveInfinity, 0.0)]
    [InlineData(0.0, 0.0)]
    [InlineData(650.5, 650.5)]
    public void TestSerializeCashIsFiniteAndNotNegative(double cash, double expected)
    {
        var node = Parse(SnapshotJson.Serialize(ValidSnapshot(cash: cash)));

        Assert.Equal(expected, node["cash"]!.GetValue<double>());
    }

    [Fact]
    public void TestSerializeNegativeLivesBecomeZero()
    {
        var node = Parse(SnapshotJson.Serialize(ValidSnapshot(lives: -1)));

        Assert.Equal(0.0, node["lives"]!.GetValue<double>());
    }

    [Theory]
    [InlineData(0, 1)]
    [InlineData(39, 40)]
    [InlineData(-1, 1)]
    public void TestRoundFromGame(int zeroBased, int expected)
    {
        Assert.Equal(expected, GameSnapshot.RoundFromGame(zeroBased));
    }
}
