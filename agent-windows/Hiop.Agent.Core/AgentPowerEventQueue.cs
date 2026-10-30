using System.Text.Json;

namespace Hiop.Agent.Core;

public sealed class AgentPowerEventQueue
{
    private sealed class State
    {
        public DateOnly? LastNudgeDate { get; set; }
        public DateOnly? LastPromptDate { get; set; }
        public List<AgentPowerEvent> PendingEvents { get; set; } = [];
    }

    private static readonly JsonSerializerOptions JsonOptions = AgentJson.Api;
    private readonly string _path;
    private readonly object _gate = new();
    private State _state;

    public AgentPowerEventQueue(string dataDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(dataDirectory);
        Directory.CreateDirectory(dataDirectory);
        _path = Path.Combine(dataDirectory, "power-events.json");
        _state = File.Exists(_path)
            ? JsonSerializer.Deserialize<State>(File.ReadAllText(_path), JsonOptions)
                ?? throw new InvalidDataException("The saved HIOP power event queue is empty.")
            : new State();
    }

    public IReadOnlyList<AgentPowerEvent> PendingEvents
    {
        get
        {
            lock (_gate)
            {
                return _state.PendingEvents.ToArray();
            }
        }
    }

    public bool QueueDailyEvent(string eventType, DateOnly localDate, bool isPrompt)
    {
        lock (_gate)
        {
            if (isPrompt && _state.LastPromptDate == localDate ||
                !isPrompt && _state.LastNudgeDate == localDate)
            {
                return false;
            }

            var next = CopyState();
            if (isPrompt)
            {
                next.LastPromptDate = localDate;
            }
            else
            {
                next.LastNudgeDate = localDate;
            }

            next.PendingEvents.Add(CreateEvent(eventType));
            Save(next);
            _state = next;
            return true;
        }
    }

    public AgentPowerEvent QueueEvent(string eventType, string? reason = null)
    {
        lock (_gate)
        {
            var next = CopyState();
            var powerEvent = CreateEvent(eventType, reason);
            next.PendingEvents.Add(powerEvent);
            Save(next);
            _state = next;
            return powerEvent;
        }
    }

    public void Acknowledge(Guid eventId)
    {
        lock (_gate)
        {
            var next = CopyState();
            var removed = next.PendingEvents.RemoveAll(item => item.EventId == eventId);
            if (removed == 0)
            {
                return;
            }

            Save(next);
            _state = next;
        }
    }

    private State CopyState() => new()
    {
        LastNudgeDate = _state.LastNudgeDate,
        LastPromptDate = _state.LastPromptDate,
        PendingEvents = [.. _state.PendingEvents],
    };

    private void Save(State state)
    {
        var temporaryPath = _path + ".tmp";
        try
        {
            File.WriteAllText(temporaryPath, JsonSerializer.Serialize(state, JsonOptions));
            File.Move(temporaryPath, _path, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporaryPath))
            {
                File.Delete(temporaryPath);
            }
        }
    }

    private static AgentPowerEvent CreateEvent(string eventType, string? reason = null) =>
        new(Guid.NewGuid(), eventType, DateTimeOffset.UtcNow, reason);
}
