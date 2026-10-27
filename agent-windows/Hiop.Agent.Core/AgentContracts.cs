using System.Text.Json;

namespace Hiop.Agent.Core;

public static class AgentControlPipe
{
    public const string Name = "hiop-agent-control";
}

public static class AgentDeviceActionPipe
{
    public const string Name = "hiop-agent-device-actions";
}

public static class AgentPrivilegedActionPipe
{
    public const string Name = "hiop-agent-privileged-actions";
}

public static class AgentJson
{
    public static JsonSerializerOptions Api { get; } = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };
}

public sealed record AgentControlRequest(string Action, string? EnrollmentToken = null);

public sealed record AgentControlResponse(
    bool Ok,
    string Status,
    string Message,
    bool Enrolled = false,
    int PendingQueue = 0,
    DateTimeOffset? LastHeartbeat = null);

public sealed record AgentDeviceActionRequest(string Action);

public sealed record AgentDeviceActionResponse(bool Succeeded, string Message);

public sealed record AgentEnrollmentRequest(string EnrollmentToken, string Hostname, string Version, int ApiVersion = 1);

public sealed record AgentEnrollmentResponse(string AgentId, string Credential, Guid OrganizationId, Guid PropertyId, int AgentApiVersion);

public sealed record AgentHeartbeatRequest(
    string Version,
    string Hostname,
    long UptimeSeconds,
    int PendingQueue,
    int QueueCapacity,
    string? LastSuccessfulJob,
    double? CpuPercent,
    long? MemoryTotalBytes,
    long? MemoryFreeBytes,
    long? DiskFreeBytes,
    string? IpAddress,
    string? OperatingSystem,
    string? LoggedUser,
    DateTimeOffset? LastUpdate);

public sealed record AgentHeartbeatResponse(string Status, DateTimeOffset ServerTime, int AgentApiVersion);

public sealed record AgentJob(Guid Id, string Type, JsonElement Payload, int TimeoutSeconds);

public sealed record AgentJobStatusResponse(string Status);

public sealed record AgentJobUpdateRequest(string Status, string? Error = null);

public sealed record AgentObservation(
    string ObservationId,
    string Source,
    DateTimeOffset ObservedAt,
    int SchemaVersion,
    JsonElement Payload);

public sealed record AgentObservationEnvelope(
    string ObservationId,
    string Source,
    DateTimeOffset ObservedAt,
    int SchemaVersion,
    JsonElement Payload);

public sealed record AgentQueuedObservation(string FilePath, AgentObservation Observation);
