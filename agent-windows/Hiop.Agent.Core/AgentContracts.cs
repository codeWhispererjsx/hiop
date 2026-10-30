using System.Text.Json;

namespace Hiop.Agent.Core;

public static class AgentControlPipe
{
    public const string Name = "hiop-agent-control";
}

public static class AgentJson
{
    public static JsonSerializerOptions Api { get; } = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };
}

public sealed record AgentControlRequest(
    string Action,
    string? EnrollmentToken = null,
    Guid? NoticeId = null,
    AgentPowerEvent? PowerEvent = null);

public sealed record AgentControlResponse(
    bool Ok,
    string Status,
    string Message,
    bool Enrolled = false,
    int PendingQueue = 0,
    DateTimeOffset? LastHeartbeat = null,
    IReadOnlyList<AgentNotice>? Notices = null,
    int? SmartLockTimeoutSeconds = null);

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
    DateTimeOffset? LastUpdate,
    bool? FastStartupEnabled = null,
    string? LidCloseAction = null,
    double? BatteryHealthPercent = null,
    int? PendingWindowsUpdates = null,
    DateTimeOffset? LastShutdownAt = null);

public sealed record AgentHeartbeatResponse(
    string Status,
    DateTimeOffset ServerTime,
    int AgentApiVersion,
    int? SmartLockTimeoutSeconds = null);

public sealed record AgentJob(Guid Id, string Type, JsonElement Payload, int TimeoutSeconds);

public sealed record AgentPowerEvent(Guid EventId, string EventType, DateTimeOffset OccurredAt, string? Reason = null);

public sealed record AgentNotice(Guid Id, string Message);

public sealed record AgentNoticeAcknowledgement(string Status);

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
