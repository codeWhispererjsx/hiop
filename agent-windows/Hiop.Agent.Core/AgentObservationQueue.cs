using System.Text.Json;
using System.Globalization;

namespace Hiop.Agent.Core;

public sealed class AgentObservationQueue(string dataDirectory)
{
    private const int MaximumItems = 10000;
    private static readonly TimeSpan Retention = TimeSpan.FromDays(7);
    private static readonly JsonSerializerOptions JsonOptions = AgentJson.Api;
    private readonly string _queueDirectory = Path.Combine(dataDirectory, "queue");
    private readonly object _gate = new();

    public int Count
    {
        get
        {
            lock (_gate)
            {
                return Directory.Exists(_queueDirectory)
                    ? Directory.EnumerateFiles(_queueDirectory, "*.json").Count()
                    : 0;
            }
        }
    }

    public bool Contains(string observationId)
    {
        lock (_gate)
        {
            return File.Exists(Path.Combine(_queueDirectory, observationId + ".json"));
        }
    }

    public string Enqueue(string source, object payload)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(source);
        Directory.CreateDirectory(_queueDirectory);
        var id = $"{DateTime.UtcNow.Ticks.ToString("D19", CultureInfo.InvariantCulture)}-{Guid.NewGuid():N}";
        var envelope = new AgentObservationEnvelope(
            id,
            source,
            DateTimeOffset.UtcNow,
            1,
            JsonSerializer.SerializeToElement(payload, JsonOptions));
        var targetPath = Path.Combine(_queueDirectory, id + ".json");
        var temporaryPath = targetPath + ".tmp";
        var json = JsonSerializer.Serialize(envelope, JsonOptions);

        lock (_gate)
        {
            PruneExpired();
            if (Directory.EnumerateFiles(_queueDirectory, "*.json").Take(MaximumItems).Count() >= MaximumItems)
            {
                throw new InvalidOperationException($"The local observation queue is full ({MaximumItems} items).");
            }

            try
            {
                File.WriteAllText(temporaryPath, json);
                File.Move(temporaryPath, targetPath);
            }
            finally
            {
                if (File.Exists(temporaryPath))
                {
                    File.Delete(temporaryPath);
                }
            }
        }

        return id;
    }

    public IReadOnlyList<AgentQueuedObservation> ReadReady(int limit = 50)
    {
        if (limit is < 1 or > 1000)
        {
            throw new ArgumentOutOfRangeException(nameof(limit));
        }

        lock (_gate)
        {
            if (!Directory.Exists(_queueDirectory))
            {
                return [];
            }

            PruneExpired();
            return Directory.EnumerateFiles(_queueDirectory, "*.json")
                .OrderBy(path => path, StringComparer.Ordinal)
                .Take(limit)
                .Select(path =>
                {
                    var json = File.ReadAllText(path);
                    var observation = JsonSerializer.Deserialize<AgentObservation>(json, JsonOptions)
                        ?? throw new InvalidDataException($"Queued observation file '{Path.GetFileName(path)}' is empty.");
                    return new AgentQueuedObservation(path, observation);
                })
                .ToArray();
        }
    }

    public void Acknowledge(AgentQueuedObservation item)
    {
        lock (_gate)
        {
            if (File.Exists(item.FilePath))
            {
                File.Delete(item.FilePath);
            }
        }
    }

    private void PruneExpired()
    {
        var cutoff = DateTime.UtcNow - Retention;
        foreach (var path in Directory.EnumerateFiles(_queueDirectory, "*.json"))
        {
            if (File.GetCreationTimeUtc(path) < cutoff)
            {
                File.Delete(path);
            }
        }
    }
}
