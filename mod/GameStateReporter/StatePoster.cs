using System;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using MelonLoader;

namespace GameStateReporter;

/// <summary>
/// Fire-and-forget POST of a snapshot. At most one request is in flight; failures are logged at
/// most once per minute and never thrown into the game loop.
/// </summary>
internal sealed class StatePoster
{
    private static readonly HttpClient Client = new() { Timeout = TimeSpan.FromSeconds(1) };

    private readonly RateLimitedLog failureLog = new(TimeSpan.FromMinutes(1));
    private int busy;

    /// <summary>Returns false when a previous post is still running, so the caller can retry next tick.</summary>
    public bool TryPost(string url, string json)
    {
        if (Interlocked.Exchange(ref busy, 1) == 1)
        {
            return false;
        }
        Task.Run(() => SendAsync(url, json));
        return true;
    }

    private async Task SendAsync(string url, string json)
    {
        try
        {
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            using var response = await Client.PostAsync(url, content).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                ReportFailure($"{url} answered {(int)response.StatusCode}: {body}");
            }
        }
        catch (Exception error)
        {
            ReportFailure($"could not reach {url} ({error.GetType().Name}: {error.Message}). Is \"python -m btd6 serve\" running?");
        }
        finally
        {
            Interlocked.Exchange(ref busy, 0);
        }
    }

    public void ReportFailure(string message)
    {
        if (failureLog.ShouldLog(DateTime.UtcNow))
        {
            MelonLogger.Warning($"{message}");
        }
    }
}
