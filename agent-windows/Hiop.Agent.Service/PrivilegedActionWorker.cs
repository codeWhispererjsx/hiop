using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;
using Hiop.Agent.Core;

namespace Hiop.Agent.Service;

public sealed class PrivilegedActionWorker(ILogger<PrivilegedActionWorker> logger) : BackgroundService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await using var pipe = CreatePipe();
                await pipe.WaitForConnectionAsync(stoppingToken);
                using var reader = new StreamReader(pipe, leaveOpen: true);
                await using var writer = new StreamWriter(pipe, leaveOpen: true) { AutoFlush = true };
                var line = await reader.ReadLineAsync(stoppingToken);
                var response = HandleRequest(line);
                await writer.WriteLineAsync(JsonSerializer.Serialize(response, JsonOptions).AsMemory(), stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                logger.LogWarning("Privileged HIOP action pipe failed: {Message}", exception.Message);
            }
        }
    }

    private static NamedPipeServerStream CreatePipe()
    {
        var security = new PipeSecurity();
        security.AddAccessRule(new PipeAccessRule(
            (SecurityIdentifier)new NTAccount(@"NT SERVICE\HIOPAgent").Translate(typeof(SecurityIdentifier)),
            PipeAccessRights.ReadWrite,
            AccessControlType.Allow));
        security.AddAccessRule(new PipeAccessRule(
            new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null),
            PipeAccessRights.ReadWrite,
            AccessControlType.Allow));
        return NamedPipeServerStreamAcl.Create(
            AgentPrivilegedActionPipe.Name,
            PipeDirection.InOut,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous,
            1024,
            1024,
            security);
    }

    private static AgentDeviceActionResponse HandleRequest(string? line)
    {
        if (string.IsNullOrWhiteSpace(line) || line.Length > 512)
        {
            return new AgentDeviceActionResponse(false, "The privileged action request is invalid.");
        }

        AgentDeviceActionRequest? request;
        try
        {
            request = JsonSerializer.Deserialize<AgentDeviceActionRequest>(line, JsonOptions);
        }
        catch (JsonException)
        {
            return new AgentDeviceActionResponse(false, "The privileged action request is invalid.");
        }

        if (request?.Action is not ("RESTART" or "SHUTDOWN" or "ENABLE_RDP" or "DISABLE_RDP" or "TRIGGER_WINDOWS_UPDATE"))
        {
            return new AgentDeviceActionResponse(false, "The requested privileged action is not allowlisted.");
        }

        return WindowsDeviceActionRunner.Run(request.Action);
    }
}
