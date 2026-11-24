using System;
using GameStateReporter;
using Xunit;

namespace GameStateReporter.Tests;

public class SendPolicyTests
{
    private static readonly DateTime Start = new(2026, 11, 24, 12, 0, 0, DateTimeKind.Utc);

    private static SendPolicy NewPolicy() => new(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(5));

    private static DateTime After(double seconds) => Start.AddSeconds(seconds);

    [Fact]
    public void TestShouldReadFirstTime()
    {
        Assert.True(NewPolicy().ShouldRead(Start));
    }

    [Fact]
    public void TestShouldReadWithinIntervalIsThrottled()
    {
        var policy = NewPolicy();
        policy.ShouldRead(Start);

        Assert.False(policy.ShouldRead(After(0.5)));
        Assert.True(policy.ShouldRead(After(1)));
    }

    [Fact]
    public void TestShouldReadDirtySkipsThrottle()
    {
        var policy = NewPolicy();
        policy.ShouldRead(Start);
        policy.MarkDirty();

        Assert.True(policy.ShouldRead(After(0.1)));
        Assert.False(policy.ShouldRead(After(0.2)));
    }

    [Fact]
    public void TestShouldSendNothingSentYet()
    {
        Assert.True(NewPolicy().ShouldSend("{}", Start));
    }

    [Fact]
    public void TestShouldSendUnchangedBeforeHeartbeat()
    {
        var policy = NewPolicy();
        policy.RecordSent("{\"round\":1}", Start);

        Assert.False(policy.ShouldSend("{\"round\":1}", After(4.9)));
    }

    [Fact]
    public void TestShouldSendUnchangedAtHeartbeat()
    {
        var policy = NewPolicy();
        policy.RecordSent("{\"round\":1}", Start);

        Assert.True(policy.ShouldSend("{\"round\":1}", After(5)));
    }

    [Fact]
    public void TestShouldSendChanged()
    {
        var policy = NewPolicy();
        policy.RecordSent("{\"round\":1}", Start);

        Assert.True(policy.ShouldSend("{\"round\":2}", After(0.1)));
    }

    [Fact]
    public void TestShouldSendNotRecordedIsSentAgain()
    {
        var policy = NewPolicy();
        policy.RecordSent("{\"round\":1}", Start);

        Assert.True(policy.ShouldSend("{\"round\":2}", After(0.1)));
        Assert.True(policy.ShouldSend("{\"round\":2}", After(0.2)));
    }

    [Fact]
    public void TestResetForgetsLastSend()
    {
        var policy = NewPolicy();
        policy.ShouldRead(Start);
        policy.RecordSent("{\"round\":1}", Start);

        policy.Reset();

        Assert.True(policy.ShouldRead(After(0.1)));
        Assert.True(policy.ShouldSend("{\"round\":1}", After(0.1)));
    }
}

public class RateLimitedLogTests
{
    private static readonly DateTime Start = new(2026, 11, 24, 12, 0, 0, DateTimeKind.Utc);

    [Fact]
    public void TestShouldLogOncePerInterval()
    {
        var log = new RateLimitedLog(TimeSpan.FromMinutes(1));

        Assert.True(log.ShouldLog(Start));
        Assert.False(log.ShouldLog(Start.AddSeconds(59)));
        Assert.True(log.ShouldLog(Start.AddSeconds(60)));
    }
}
