using System.Collections.Generic;
using BTD_Mod_Helper.Extensions;
using Il2CppAssets.Scripts.Simulation.Towers;
using Il2CppAssets.Scripts.Unity.UI_New.InGame;

namespace GameStateReporter;

/// <summary>Reads the running match into a <see cref="GameSnapshot"/>. Must run on the game's main thread.</summary>
internal static class GameReader
{
    /// <summary>Returns null outside a match (main menu, loading screens).</summary>
    public static GameSnapshot? TryRead()
    {
        var game = InGame.instance;
        if (game == null || game.bridge == null)
        {
            return null;
        }
        return new GameSnapshot
        {
            Round = GameSnapshot.RoundFromGame(game.bridge.GetCurrentRound()),
            Cash = game.GetCash(),
            Lives = game.GetHealth(),
            Difficulty = game.SelectedDifficulty ?? "",
            Mode = game.SelectedMode ?? "",
            Map = game.SelectedMap ?? "",
            Towers = ReadTowers(game),
        };
    }

    private static List<TowerSnapshot> ReadTowers(InGame game)
    {
        var towers = new List<TowerSnapshot>();
        foreach (var tower in game.GetTowers())
        {
            var snapshot = ReadTower(tower);
            if (snapshot != null)
            {
                towers.Add(snapshot);
            }
        }
        return towers;
    }

    /// <summary>Skips sub-towers (e.g. Engineer sentries, Etienne's drones) that the player did not buy.</summary>
    private static TowerSnapshot? ReadTower(Tower tower)
    {
        var model = tower?.towerModel;
        if (model == null || model.isSubTower || string.IsNullOrEmpty(model.baseId))
        {
            return null;
        }
        var tiers = new List<int>();
        if (model.tiers != null)
        {
            for (var position = 0; position < model.tiers.Length; position++)
            {
                tiers.Add(model.tiers[position]);
            }
        }
        return new TowerSnapshot(model.baseId, tiers);
    }
}
