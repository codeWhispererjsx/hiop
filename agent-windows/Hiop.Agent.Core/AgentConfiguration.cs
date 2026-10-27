using System.Text.Json;

namespace Hiop.Agent.Core;

public sealed record AgentConfiguration(string BackendUrl, string AgentName, int HeartbeatSeconds = 30, int PollSeconds = 5)
{
    public const string Version = "1.2.0";
    public static string DefaultPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
        "HIOP",
        "Agent",
        "agent.json");

    public static string DefaultDataDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
        "HIOP",
        "Agent",
        "State");

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static AgentConfiguration Load(string path)
    {
        var json = File.ReadAllText(path);
        var configuration = JsonSerializer.Deserialize<AgentConfiguration>(json, JsonOptions)
            ?? throw new InvalidDataException("The HIOP agent configuration is empty.");
        configuration.Validate();
        return configuration;
    }

    public void Validate()
    {
        if (!Uri.TryCreate(BackendUrl, UriKind.Absolute, out var backend) ||
            (backend.Scheme != Uri.UriSchemeHttps &&
             !(backend.Scheme == Uri.UriSchemeHttp && backend.IsLoopback)))
        {
            throw new InvalidDataException("The HIOP agent backend URL must use HTTPS. HTTP is allowed only for localhost development.");
        }

        if (string.IsNullOrWhiteSpace(AgentName) || AgentName.Length > 160)
        {
            throw new InvalidDataException("The HIOP agent name must be between 1 and 160 characters.");
        }

        if (HeartbeatSeconds is < 10 or > 120 || PollSeconds is < 2 or > 60)
        {
            throw new InvalidDataException("The HIOP agent timing settings are outside the supported range.");
        }
    }
}
