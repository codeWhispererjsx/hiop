using Hiop.Agent.Core;

namespace Hiop.Agent.Service;

public sealed class AgentRuntimeStatus
{
    private readonly object _gate = new();
    private string _status = "Starting";
    private string _message = "HIOP agent service is starting.";
    private DateTimeOffset? _lastHeartbeat;
    private string? _lastSuccessfulJob;
    private int? _smartLockTimeoutSeconds;

    public AgentControlResponse Snapshot(AgentCredentialStore credentials, AgentObservationQueue queue)
    {
        lock (_gate)
        {
            return new AgentControlResponse(
                true,
                _status,
                _message,
                credentials.Exists,
                queue.Count,
                _lastHeartbeat,
                SmartLockTimeoutSeconds: _smartLockTimeoutSeconds);
        }
    }

    public void Set(
        string status,
        string message,
        DateTimeOffset? heartbeat = null,
        string? lastSuccessfulJob = null,
        int? smartLockTimeoutSeconds = null)
    {
        lock (_gate)
        {
            _status = status;
            _message = message;
            if (heartbeat.HasValue)
            {
                _lastHeartbeat = heartbeat;
            }

            if (lastSuccessfulJob is not null)
            {
                _lastSuccessfulJob = lastSuccessfulJob;
            }

            if (smartLockTimeoutSeconds.HasValue)
            {
                _smartLockTimeoutSeconds = smartLockTimeoutSeconds;
            }
        }
    }

    public string CurrentStatus
    {
        get
        {
            lock (_gate)
            {
                return _status;
            }
        }
    }

    public string? LastSuccessfulJob
    {
        get
        {
            lock (_gate)
            {
                return _lastSuccessfulJob;
            }
        }
    }
}
