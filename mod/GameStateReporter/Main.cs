using System;
using BTD_Mod_Helper;
using BTD_Mod_Helper.Api.ModOptions;
using GameStateReporter;
using Il2CppAssets.Scripts.Models;
using Il2CppAssets.Scripts.Models.Towers;
using Il2CppAssets.Scripts.Simulation.Objects;
using Il2CppAssets.Scripts.Simulation.Towers;
using MelonLoader;

[assembly: MelonInfo(typeof(GameStateReporterMod), ModHelperData.Name, ModHelperData.Version, ModHelperData.RepoOwner)]
[assembly: MelonGame("Ninja Kiwi", "BloonsTD6")]

namespace GameStateReporter;

/// <summary>
/// Reports the live game to the BTD6 Tower Stats server (docs/game-state.md). The state is read
/// at most once a second (at once after a round starts or a tower is bought, upgraded or sold),
/// posted when it changes, and re-posted every 5 seconds as a heartbeat.
/// </summary>
public class GameStateReporterMod : BloonsTD6Mod
{
    public static readonly ModSettingBool Enabled = new(true)
    {
        description = "Send the live game state to the BTD6 Tower Stats server.",
    };

    public static readonly ModSettingString ServerUrl = new("http://127.0.0.1:8000/api/game-state")
    {
        description = "POST endpoint of \"python -m btd6 serve\". Change it to reach another PC on your network.",
    };

    private readonly SendPolicy policy = new(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(5));
    private readonly StatePoster poster = new();

    public override void OnApplicationStart()
    {
        MelonLogger.Msg($"Reporting to {(string)ServerUrl}. Offline/solo play only.");
    }

    public override void OnUpdate()
    {
        if (!Enabled)
        {
            return;
        }
        var now = DateTime.UtcNow;
        if (!policy.ShouldRead(now))
        {
            return;
        }
        var snapshot = ReadSafely();
        if (snapshot == null)
        {
            policy.Reset();
            return;
        }
        var json = SnapshotJson.Serialize(snapshot);
        if (policy.ShouldSend(json, now) && poster.TryPost(ServerUrl, json))
        {
            policy.RecordSent(json, now);
        }
    }

    private GameSnapshot? ReadSafely()
    {
        try
        {
            return GameReader.TryRead();
        }
        catch (Exception error)
        {
            poster.ReportFailure($"could not read the game state ({error.GetType().Name}: {error.Message})");
            return null;
        }
    }

    public override void OnRoundStart() => policy.MarkDirty();

    public override void OnTowerCreated(Tower tower, Entity target, Model modelToUse) => policy.MarkDirty();

    public override void OnTowerUpgraded(Tower tower, string upgradeName, TowerModel newBaseTowerModel) =>
        policy.MarkDirty();

    public override void OnTowerSold(Tower tower, float amount) => policy.MarkDirty();
}
