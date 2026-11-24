using System;

namespace GameStateReporter;

/// <summary>
/// Decides when the mod reads and posts the game state. The state is read at most once per
/// <see cref="ReadInterval"/> unless something marked it dirty (round start, tower bought or
/// upgraded). A read snapshot is posted when it differs from the last one sent, or when
/// <see cref="HeartbeatInterval"/> has passed, so the server can tell a running game from a closed one.
/// </summary>
public sealed class SendPolicy
{
    private DateTime? lastRead;
    private DateTime? lastSent;
    private string? lastJson;
    private bool dirty;

    public SendPolicy(TimeSpan readInterval, TimeSpan heartbeatInterval)
    {
        ReadInterval = readInterval;
        HeartbeatInterval = heartbeatInterval;
    }

    public TimeSpan ReadInterval { get; }

    public TimeSpan HeartbeatInterval { get; }

    public void MarkDirty() => dirty = true;

    /// <summary>Forget everything, e.g. after leaving a game, so the next game is sent at once.</summary>
    public void Reset()
    {
        lastRead = null;
        lastSent = null;
        lastJson = null;
        dirty = false;
    }

    public bool ShouldRead(DateTime now)
    {
        if (!dirty && lastRead is { } previous && now - previous < ReadInterval)
        {
            return false;
        }
        lastRead = now;
        dirty = false;
        return true;
    }

    public bool ShouldSend(string json, DateTime now)
    {
        if (lastSent is not { } previous || json != lastJson)
        {
            return true;
        }
        return now - previous >= HeartbeatInterval;
    }

    public void RecordSent(string json, DateTime now)
    {
        lastJson = json;
        lastSent = now;
    }
}
