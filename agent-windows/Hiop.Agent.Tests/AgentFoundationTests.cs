using System.Net;
using System.Text.Json;
using Hiop.Agent.Core;
using Hiop.Agent.Service;

namespace Hiop.Agent.Tests;

public sealed class AgentFoundationTests
{
    [Fact]
    public void ConfigurationRequiresHttpsExceptForLocalDevelopment()
    {
        new AgentConfiguration("https://hiop.example", "Site server").Validate();
        new AgentConfiguration("http://127.0.0.1:8000", "Local agent").Validate();

        Assert.Throws<InvalidDataException>(
            () => new AgentConfiguration("http://hiop.example", "Site server").Validate());
    }

    [Fact]
    public void ConfigurationRejectsUnsupportedPollingIntervals()
    {
        Assert.Throws<InvalidDataException>(
            () => new AgentConfiguration("https://hiop.example", "Site server", HeartbeatSeconds: 5).Validate());
    }

    [Fact]
    public void AgentApiPayloadUsesTheBackendSnakeCaseContract()
    {
        var request = new AgentEnrollmentRequest("one-time-token", "workstation", "1.0.0");

        var json = JsonSerializer.Serialize(request, AgentJson.Api);

        Assert.Contains("\"enrollment_token\"", json);
        Assert.Contains("\"api_version\"", json);
        Assert.DoesNotContain("\"enrollmentToken\"", json);
    }

    [Fact]
    public void ObservationQueuePersistsAndAcknowledgesObservations()
    {
        var directory = Path.Combine(Path.GetTempPath(), "hiop-agent-tests", Guid.NewGuid().ToString("N"));
        try
        {
            var queue = new AgentObservationQueue(directory);
            var id = queue.Enqueue("discovery", new { job_id = Guid.NewGuid(), result = new { scanned = 1 } });

            var item = Assert.Single(queue.ReadReady());
            Assert.Equal(id, item.Observation.ObservationId);
            Assert.Equal("discovery", item.Observation.Source);
            Assert.Equal(1, item.Observation.Payload.GetProperty("result").GetProperty("scanned").GetInt32());

            queue.Acknowledge(item);
            Assert.Empty(queue.ReadReady());
            Assert.Equal(0, queue.Count);
        }
        finally
        {
            if (Directory.Exists(directory))
            {
                Directory.Delete(directory, recursive: true);
            }
        }
    }

    [Fact]
    public void PowerEventQueuePersistsDailyPromptsAndRetriesUntilAcknowledged()
    {
        var directory = Path.Combine(Path.GetTempPath(), "hiop-agent-tests", Guid.NewGuid().ToString("N"));
        try
        {
            var queue = new AgentPowerEventQueue(directory);
            var today = DateOnly.FromDateTime(DateTime.Now);

            Assert.True(queue.QueueDailyEvent("END_OF_DAY_NUDGE", today, isPrompt: false));
            Assert.False(queue.QueueDailyEvent("END_OF_DAY_NUDGE", today, isPrompt: false));
            var pending = Assert.Single(queue.PendingEvents);
            Assert.Equal("END_OF_DAY_NUDGE", pending.EventType);

            var afterRestart = new AgentPowerEventQueue(directory);
            Assert.Single(afterRestart.PendingEvents);
            afterRestart.Acknowledge(pending.EventId);
            Assert.Empty(new AgentPowerEventQueue(directory).PendingEvents);
        }
        finally
        {
            if (Directory.Exists(directory))
            {
                Directory.Delete(directory, recursive: true);
            }
        }
    }

    [Theory]
    [InlineData(59, 0, false)]
    [InlineData(60, 0, true)]
    [InlineData(600, 1, false)]
    public void AutomaticShutdownRequiresVerifiedIdleAndNoOpenWindows(int idleSeconds, int openWindows, bool expected)
    {
        var applications = Enumerable.Range(0, openWindows).Select(index => $"application-{index}").ToArray();

        Assert.Equal(
            expected,
            WindowsPowerPolicy.CanAutomaticallyShutDown(TimeSpan.FromSeconds(idleSeconds), applications));
    }

    [Fact]
    public void AutomaticShutdownFailsClosedWhenIdleOrWindowStateIsUnknown()
    {
        Assert.False(WindowsPowerPolicy.CanAutomaticallyShutDown(null, []));
        Assert.False(WindowsPowerPolicy.CanAutomaticallyShutDown(TimeSpan.FromMinutes(2), null));
    }

    [Theory]
    [InlineData("EXCEL", false, true)]
    [InlineData("unknown-editor", true, true)]
    [InlineData("explorer", true, true)]
    [InlineData("shellexperiencehost", true, false)]
    [InlineData("svchost", false, false)]
    public void ShutdownSafetyBlocksKnownWorkAppsAndUnknownVisibleWindows(
        string processName,
        bool hasVisibleWindow,
        bool expected)
    {
        Assert.Equal(expected, WindowsPowerPolicy.IsPotentialUnsavedWork(processName, hasVisibleWindow));
    }

    [Fact]
    public void DiscoveryRangesAreBoundedAndEnumerateUsableAddresses()
    {
        var hosts = AgentJobExecutor.EnumerateHosts("192.168.10.0/30", 4);

        Assert.Equal(
            [IPAddress.Parse("192.168.10.1"), IPAddress.Parse("192.168.10.2")],
            hosts);
        Assert.Throws<InvalidOperationException>(
            () => AgentJobExecutor.EnumerateHosts("10.0.0.0/8", 1024));
    }

    [Fact]
    public void DiscoverySupportsSmallIpv6Networks()
    {
        var hosts = AgentJobExecutor.EnumerateHosts("2001:db8::/126", 4);

        Assert.Equal(
            new[] { IPAddress.Parse("2001:db8::1"), IPAddress.Parse("2001:db8::2"), IPAddress.Parse("2001:db8::3") },
            hosts);
    }

    [Fact]
    public async Task JobExecutorRejectsUnlistedJobTypes()
    {
        var payload = JsonSerializer.SerializeToElement(new { });
        var job = new AgentJob(Guid.NewGuid(), "EXECUTE_COMMAND", payload, 10);

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => AgentJobExecutor.ExecuteAsync(job, CancellationToken.None));
    }

    [Fact]
    public async Task AgentRejectsLegacyEndpointControlJobs()
    {
        var payload = JsonSerializer.SerializeToElement(new { action = "SHUTDOWN" });
        var job = new AgentJob(Guid.NewGuid(), "DEVICE_ACTION", payload, 10);

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => AgentJobExecutor.ExecuteAsync(job, CancellationToken.None));
    }

    [Fact]
    public void DiscoveryAssociatesValidatedArpMacAddressesWithTargets()
    {
        var devices = new[]
        {
            new Dictionary<string, object?> { ["target"] = "10.20.0.5" },
            new Dictionary<string, object?> { ["target"] = "10.20.0.6" },
        };
        var arpEntries = new[]
        {
            new Dictionary<string, object?> { ["ip"] = "10.20.0.5", ["mac"] = "00-11-22-33-44-55" },
            new Dictionary<string, object?> { ["ip"] = "10.20.0.6", ["mac"] = "invalid" },
        };

        AgentJobExecutor.EnrichWithMacAddresses(devices, arpEntries);

        Assert.Equal("00:11:22:33:44:55", devices[0]["mac_address"]);
        Assert.False(devices[1].ContainsKey("mac_address"));
    }

    [Theory]
    [InlineData("00-11-22-33-44-55", "00:11:22:33:44:55")]
    [InlineData("000000000000", null)]
    [InlineData("not-a-mac", null)]
    public void LocalInventoryNormalizesOnlyUsableMacAddresses(string input, string? expected)
    {
        Assert.Equal(expected, LocalWindowsInventory.NormalizeMac(input));
    }

    [Fact]
    public void LocalWindowsInventoryReadsSystemIdentity()
    {
        var inventory = LocalWindowsInventory.Collect();

        Assert.Equal(Environment.MachineName, inventory["hostname"]);
        Assert.IsType<Dictionary<string, object?>[]>(inventory["network_adapters"]);
    }
}
