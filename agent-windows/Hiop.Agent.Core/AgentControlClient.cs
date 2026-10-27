using System.IO.Pipes;
using System.Text.Json;

namespace Hiop.Agent.Core;

public static class AgentControlClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static async Task<AgentControlResponse> SendAsync(
        AgentControlRequest request,
        CancellationToken cancellationToken = default)
    {
        await using var pipe = new NamedPipeClientStream(
            ".",
            AgentControlPipe.Name,
            PipeDirection.InOut,
            PipeOptions.Asynchronous);
        await pipe.ConnectAsync(3000, cancellationToken);

        using var reader = new StreamReader(pipe, leaveOpen: true);
        await using var writer = new StreamWriter(pipe, leaveOpen: true) { AutoFlush = true };
        await writer.WriteLineAsync(JsonSerializer.Serialize(request, JsonOptions));
        var response = await reader.ReadLineAsync(cancellationToken)
            ?? throw new IOException("The HIOP agent service closed the control connection without responding.");
        return JsonSerializer.Deserialize<AgentControlResponse>(response, JsonOptions)
            ?? throw new InvalidDataException("The HIOP agent service returned an invalid control response.");
    }
}
