using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.Json;
using Hiop.Agent.Core;

namespace Hiop.Agent.Service;

public sealed class AgentControlWorker(
    AgentApiClient api,
    AgentCredentialStore credentials,
    AgentObservationQueue queue,
    AgentRuntimeStatus status,
    ILogger<AgentControlWorker> logger) : BackgroundService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly SemaphoreSlim _enrollmentLock = new(1, 1);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await using var server = CreatePipe();
                await server.WaitForConnectionAsync(stoppingToken);
                await HandleConnectionAsync(server, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (IOException exception)
            {
                logger.LogWarning("Agent control pipe request failed: {Message}", exception.Message);
            }
            catch (UnauthorizedAccessException exception)
            {
                logger.LogWarning("Agent control pipe access was denied: {Message}", exception.Message);
            }
        }
    }

    private static NamedPipeServerStream CreatePipe()
    {
        var security = new PipeSecurity();
        var interactiveUsers = new SecurityIdentifier(WellKnownSidType.InteractiveSid, null);
        security.AddAccessRule(new PipeAccessRule(interactiveUsers, PipeAccessRights.ReadWrite, AccessControlType.Allow));
        return NamedPipeServerStreamAcl.Create(
            AgentControlPipe.Name,
            PipeDirection.InOut,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous,
            4096,
            4096,
            security);
    }

    private async Task HandleConnectionAsync(NamedPipeServerStream pipe, CancellationToken cancellationToken)
    {
        using var reader = new StreamReader(pipe, leaveOpen: true);
        await using var writer = new StreamWriter(pipe, leaveOpen: true) { AutoFlush = true };
        string? line;
        try
        {
            line = await ReadRequestLineAsync(reader, cancellationToken);
        }
        catch (InvalidDataException)
        {
            await WriteResponseAsync(writer, new AgentControlResponse(false, "Error", "The local control request is too large."), cancellationToken);
            return;
        }

        if (string.IsNullOrWhiteSpace(line))
        {
            await WriteResponseAsync(writer, new AgentControlResponse(false, "Error", "A control request is required."), cancellationToken);
            return;
        }

        AgentControlRequest? request;
        try
        {
            request = JsonSerializer.Deserialize<AgentControlRequest>(line, JsonOptions);
        }
        catch (JsonException)
        {
            await WriteResponseAsync(writer, new AgentControlResponse(false, "Error", "The control request is invalid."), cancellationToken);
            return;
        }

        if (request is null)
        {
            await WriteResponseAsync(writer, new AgentControlResponse(false, "Error", "The control request is empty."), cancellationToken);
            return;
        }

        if (string.IsNullOrWhiteSpace(request.Action))
        {
            await WriteResponseAsync(writer, new AgentControlResponse(false, "Error", "The local control action is required."), cancellationToken);
            return;
        }

        if (request.Action.Equals("status", StringComparison.OrdinalIgnoreCase))
        {
            await WriteResponseAsync(writer, status.Snapshot(credentials, queue), cancellationToken);
            return;
        }

        if (request.Action.Equals("enroll", StringComparison.OrdinalIgnoreCase))
        {
            await EnrollAsync(request, writer, cancellationToken);
            return;
        }

        await WriteResponseAsync(writer, new AgentControlResponse(false, "Error", "Unsupported local agent action."), cancellationToken);
    }

    private async Task EnrollAsync(AgentControlRequest request, StreamWriter writer, CancellationToken cancellationToken)
    {
        if (credentials.Exists)
        {
            await WriteResponseAsync(
                writer,
                new AgentControlResponse(false, "Online", "This computer is already enrolled. Revoke the current registration before replacing it."),
                cancellationToken);
            return;
        }

        if (string.IsNullOrWhiteSpace(request.EnrollmentToken))
        {
            await WriteResponseAsync(writer, new AgentControlResponse(false, "Not enrolled", "Paste the one-time HIOP enrollment code."), cancellationToken);
            return;
        }

        if (!await _enrollmentLock.WaitAsync(0, cancellationToken))
        {
            await WriteResponseAsync(writer, new AgentControlResponse(false, "Connecting", "An enrollment is already in progress."), cancellationToken);
            return;
        }

        try
        {
            var enrollment = await api.EnrollAsync(request.EnrollmentToken.Trim(), cancellationToken);
            credentials.Save(enrollment.Credential);
            status.Set("Connecting", "Enrollment succeeded. Waiting for the first heartbeat.");
            await WriteResponseAsync(
                writer,
                new AgentControlResponse(true, "Connecting", $"Enrolled as {enrollment.AgentId}. Waiting for HIOP."),
                cancellationToken);
        }
        catch (AgentApiException exception)
        {
            status.Set("Enrollment required", "The HIOP enrollment request was rejected.");
            await WriteResponseAsync(
                writer,
                new AgentControlResponse(false, "Enrollment required", exception.Message),
                cancellationToken);
        }
        catch (HttpRequestException exception)
        {
            await WriteResponseAsync(
                writer,
                new AgentControlResponse(false, "Offline", $"Could not reach HIOP: {exception.Message}"),
                cancellationToken);
        }
        catch (CryptographicException exception)
        {
            logger.LogError("HIOP agent credential protection failed: {Message}", exception.Message);
            await WriteResponseAsync(
                writer,
                new AgentControlResponse(false, "Error", "The HIOP credential could not be protected on this computer."),
                cancellationToken);
        }
        catch (IOException exception)
        {
            logger.LogError("HIOP agent credential storage failed: {Message}", exception.Message);
            await WriteResponseAsync(
                writer,
                new AgentControlResponse(false, "Error", "The HIOP credential could not be saved on this computer."),
                cancellationToken);
        }
        finally
        {
            _enrollmentLock.Release();
        }
    }

    private static async Task WriteResponseAsync(StreamWriter writer, AgentControlResponse response, CancellationToken cancellationToken)
    {
        await writer.WriteLineAsync(JsonSerializer.Serialize(response, JsonOptions).AsMemory(), cancellationToken);
    }

    private static async Task<string?> ReadRequestLineAsync(StreamReader reader, CancellationToken cancellationToken)
    {
        const int maximumLength = 4096;
        var buffer = new char[maximumLength];
        var length = 0;
        while (true)
        {
            var read = await reader.ReadAsync(buffer.AsMemory(length, 1), cancellationToken);
            if (read == 0)
            {
                return length == 0 ? null : new string(buffer, 0, length);
            }

            if (buffer[length] == '\n')
            {
                return new string(buffer, 0, length);
            }

            if (buffer[length] == '\r')
            {
                continue;
            }

            length++;
            if (length == maximumLength)
            {
                throw new InvalidDataException("Local agent control request exceeded the size limit.");
            }
        }
    }
}
