using System;

namespace GameStateReporter;

/// <summary>Lets a failure message through at most once per interval, so a stopped server does not flood the console.</summary>
public sealed class RateLimitedLog
{
    private readonly object gate = new();
    private DateTime? lastLogged;

    public RateLimitedLog(TimeSpan interval)
    {
        Interval = interval;
    }

    public TimeSpan Interval { get; }

    public bool ShouldLog(DateTime now)
    {
        lock (gate)
        {
            if (lastLogged is { } previous && now - previous < Interval)
            {
                return false;
            }
            lastLogged = now;
            return true;
        }
    }
}
