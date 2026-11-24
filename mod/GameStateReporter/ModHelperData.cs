namespace GameStateReporter;

/// <summary>Metadata BTD Mod Helper reads for its mod list.</summary>
public static class ModHelperData
{
    public const string Version = "1.0.0";
    public const string Name = "GameStateReporter";
    public const string Description =
        "Posts the live round, cash, lives, difficulty and placed towers to the BTD6 Tower Stats " +
        "server (python -m btd6 serve) for recommendations. Offline/solo play only.";
    public const string RepoOwner = "dev-iain";
    public const string RepoName = "BloonsTD6-Stats-Database";
}
