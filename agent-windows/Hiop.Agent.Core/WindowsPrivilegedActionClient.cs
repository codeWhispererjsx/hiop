using System.IO.Pipes;
using System.Text.Json;

namespace Hiop.Agent.Core;

public static class WindowsPrivilegedActionClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static async Task<AgentDeviceActionResponse> RunAsync(string action, CancellationToken cancellationToken)
    {
        if (action is not ("RESTART" or "SHUTDOWN" or "ENABLE_RDP" or "DISABLE_RDP" or "TRIGGER_WINDOWS_UPDATE"))
        {
            throw new InvalidOperationException("The requested Windows device action is not supported.");
        }

        try
        {
            using var pipe = new NamedPipeClientStream(".", AgentPrivilegedActionPipe.Name, PipeDirection.InOut, PipeOptions.Asynchronous);
            await pipe.ConnectAsync(3000, cancellationToken);
            using var reader = new StreamReader(pipe, leaveOpen: true);
            await using var writer = new StreamWriter(pipe, leaveOpen: true) { AutoFlush = true };
            await writer.WriteLineAsync(JsonSerializer.Serialize(new AgentDeviceActionRequest(action), JsonOptions).AsMemory(), cancellationToken);
            var response = await reader.ReadLineAsync(cancellationToken);
            return response is null
                ? new AgentDeviceActionResponse(false, "The privileged action broker returned no result.")
                : JsonSerializer.Deserialize<AgentDeviceActionResponse>(response, JsonOptions)
                    ?? new AgentDeviceActionResponse(false, "The privileged action broker returned an invalid result.");
        }
        catch (Exception exception) when (exception is IOException or TimeoutException or UnauthorizedAccessException)
        {
            return new AgentDeviceActionResponse(false, $"The restricted Windows action broker is unavailable: {exception.Message}");
        }
    }
}
