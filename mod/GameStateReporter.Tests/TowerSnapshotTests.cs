using GameStateReporter;
using Xunit;

namespace GameStateReporter.Tests;

public class TowerSnapshotTests
{
    [Theory]
    [InlineData(new[] { 0, 2, 3 }, new[] { 0, 2, 3 })]
    [InlineData(new[] { 5, 5, 5 }, new[] { 5, 5, 5 })]
    [InlineData(new[] { 6, 0, 0 }, new[] { 5, 0, 0 })]
    [InlineData(new[] { -1, 0, 0 }, new[] { 0, 0, 0 })]
    [InlineData(new[] { 1, 2 }, new[] { 1, 2, 0 })]
    [InlineData(new int[0], new[] { 0, 0, 0 })]
    [InlineData(new[] { 1, 2, 3, 4 }, new[] { 1, 2, 3 })]
    public void TestClampTiers(int[] tiers, int[] expected)
    {
        Assert.Equal(expected, TowerSnapshot.ClampTiers(tiers));
    }

    [Fact]
    public void TestTowerSnapshotClampsOnConstruction()
    {
        var tower = new TowerSnapshot("SuperMonkey", new[] { 0, 0, 7 });

        Assert.Equal(new[] { 0, 0, 5 }, tower.Tiers);
        Assert.Equal("SuperMonkey", tower.BaseId);
    }
}
