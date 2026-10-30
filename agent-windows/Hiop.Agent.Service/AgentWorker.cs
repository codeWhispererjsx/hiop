using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using Hiop.Agent.Core;

namespace Hiop.Agent.Service;

public sealed class AgentWorker(
    AgentConfiguration configuration,
    AgentApiClient api,
    AgentCredentialStore credentials,
    AgentObservationQueue queue,
    AgentRuntimeStatus status,
    ILogger<AgentWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var heartbeatTask = RunHeartbeatLoopAsync(stoppingToken);
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                if (!credentials.Exists)
                {
                    if (status.CurrentStatus != "Revoked")
                    {
                        status.Set("Enrollment required", "Open HIOP Agent from the system tray and enter a one-time enrollment code.");
                    }
                    await Task.Delay(TimeSpan.FromSeconds(configuration.PollSeconds), stoppingToken);
                    continue;
                }

                try
                {
                    await FlushQueueAsync(stoppingToken);
                    foreach (var job in await api.GetJobsAsync(stoppingToken))
                    {
                        await ProcessJobAsync(job, stoppingToken);
                    }
                }
                catch (AgentApiException exception) when (exception.StatusCode == HttpStatusCode.Unauthorized)
                {
                    credentials.Delete();
                    status.Set("Revoked", "HIOP rejected this agent credential. Generate a new enrollment code to reconnect.");
                    logger.LogWarning("HIOP agent credential was rejected. Local credential removed.");
                }
                catch (HttpRequestException exception)
                {
                    status.Set("Offline", $"Cannot contact HIOP: {exception.Message}");
                    logger.LogWarning("HIOP agent request failed: {Message}", exception.Message);
                }
                catch (TaskCanceledException) when (!stoppingToken.IsCancellationRequested)
                {
                    status.Set("Offline", "HIOP did not respond in time.");
                    logger.LogWarning("HIOP agent request timed out.");
                }
                catch (Exception exception) when (exception is JsonException or InvalidDataException)
                {
                    status.Set("Offline", "HIOP returned an unexpected response. A proxy or sign-in page may be in the way.");
                    logger.LogWarning("HIOP agent response was not valid: {Message}", exception.Message);
                }
                catch (IOException exception)
                {
                    status.Set("Error", $"Local agent data could not be read or written: {exception.Message}");
                    logger.LogError("HIOP agent local data error: {Message}", exception.Message);
                }
                catch (CryptographicException exception)
                {
                    status.Set("Error", "The saved HIOP credential could not be decrypted on this computer.");
                    logger.LogError("HIOP agent credential decryption failed: {Message}", exception.Message);
                }

                await Task.Delay(TimeSpan.FromSeconds(configuration.PollSeconds), stoppingToken);
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
        }
        finally
        {
            try
            {
                await heartbeatTask;
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
            }
        }
    }

    private async Task RunHeartbeatLoopAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(configuration.HeartbeatSeconds));
        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            if (!credentials.Exists)
            {
                continue;
            }

            try
            {
                var response = await api.SendHeartbeatAsync(queue.Count, status.LastSuccessfulJob, stoppingToken);
                status.Set(
                    "Online",
                    "Connected to HIOP.",
                    DateTimeOffset.UtcNow,
                    smartLockTimeoutSeconds: response.SmartLockTimeoutSeconds);
            }
            catch (AgentApiException exception) when (exception.StatusCode == HttpStatusCode.Unauthorized)
            {
                credentials.Delete();
                status.Set("Revoked", "HIOP rejected this agent credential. Generate a new enrollment code to reconnect.");
                logger.LogWarning("HIOP agent credential was rejected during heartbeat. Local credential removed.");
            }
            catch (HttpRequestException exception)
            {
                status.Set("Offline", $"Cannot contact HIOP: {exception.Message}");
                logger.LogWarning("HIOP agent heartbeat failed: {Message}", exception.Message);
            }
            catch (TaskCanceledException) when (!stoppingToken.IsCancellationRequested)
            {
                status.Set("Offline", "HIOP did not respond in time.");
                logger.LogWarning("HIOP agent heartbeat timed out.");
            }
            catch (Exception exception) when (exception is JsonException or InvalidDataException)
            {
                status.Set("Offline", "HIOP returned an unexpected response. A proxy or sign-in page may be in the way.");
                logger.LogWarning("HIOP agent heartbeat response was not valid: {Message}", exception.Message);
            }
            catch (IOException exception)
            {
                status.Set("Error", $"Local agent credential could not be read: {exception.Message}");
                logger.LogError("HIOP agent credential read failed: {Message}", exception.Message);
            }
            catch (CryptographicException exception)
            {
                status.Set("Error", "The saved HIOP credential could not be decrypted on this computer.");
                logger.LogError("HIOP agent credential decryption failed during heartbeat: {Message}", exception.Message);
            }
        }
    }

    private async Task ProcessJobAsync(AgentJob job, CancellationToken cancellationToken)
    {
        var initialStatus = await api.GetJobStatusAsync(job.Id, cancellationToken);
        if (initialStatus.Status is "cancelled" or "cancelling")
        {
            await api.UpdateJobAsync(job.Id, new AgentJobUpdateRequest("cancelled"), cancellationToken);
            return;
        }

        var started = await api.UpdateJobAsync(job.Id, new AgentJobUpdateRequest("started"), cancellationToken);
        if (started.Status != "started")
        {
            return;
        }

        using var jobTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        using var monitorCancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        jobTimeout.CancelAfter(TimeSpan.FromSeconds(job.TimeoutSeconds));
        var cancelledByServer = 0;
        var cancellationMonitor = MonitorServerCancellationAsync(
            job.Id,
            jobTimeout,
            () => Interlocked.Exchange(ref cancelledByServer, 1),
            monitorCancellation.Token);
        try
        {
            var result = await AgentJobExecutor.ExecuteAsync(job, jobTimeout.Token);
            var observationId = queue.Enqueue(result.Source, new { job_id = job.Id, result = result.Payload });
            await FlushQueueAsync(jobTimeout.Token);

            if (queue.Contains(observationId))
            {
                status.Set("Pending upload", "The job result is queued locally and will be delivered when HIOP is reachable.");
                return;
            }

            status.Set("Online", "Connected to HIOP.", DateTimeOffset.UtcNow);
        }
        catch (OperationCanceledException) when (Volatile.Read(ref cancelledByServer) == 1)
        {
            await api.UpdateJobAsync(job.Id, new AgentJobUpdateRequest("cancelled"), cancellationToken);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            await api.UpdateJobAsync(job.Id, new AgentJobUpdateRequest("timed_out", "Agent job exceeded its time limit."), cancellationToken);
        }
        catch (Exception exception) when (exception is InvalidOperationException or FormatException or IOException or ArgumentException)
        {
            await api.UpdateJobAsync(
                job.Id,
                new AgentJobUpdateRequest("failed", exception.Message[..Math.Min(exception.Message.Length, 1000)]),
                cancellationToken);
            logger.LogWarning("HIOP agent job {JobId} failed: {Message}", job.Id, exception.Message);
        }
        finally
        {
            monitorCancellation.Cancel();
            jobTimeout.Cancel();
            try
            {
                await cancellationMonitor;
            }
            catch (OperationCanceledException) when (monitorCancellation.IsCancellationRequested)
            {
            }
        }
    }

    private async Task MonitorServerCancellationAsync(
        Guid jobId,
        CancellationTokenSource jobCancellation,
        Action markCancelled,
        CancellationToken monitorToken)
    {
        while (!jobCancellation.IsCancellationRequested && !monitorToken.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromSeconds(3), monitorToken);
            if (jobCancellation.IsCancellationRequested)
            {
                return;
            }

            try
            {
                var remote = await api.GetJobStatusAsync(jobId, monitorToken);
                if (remote.Status is "cancelling" or "cancelled")
                {
                    markCancelled();
                    jobCancellation.Cancel();
                    return;
                }
            }
            catch (HttpRequestException exception)
            {
                logger.LogWarning("Could not check cancellation for agent job {JobId}: {Message}", jobId, exception.Message);
                return;
            }
        }
    }

    private async Task FlushQueueAsync(CancellationToken cancellationToken)
    {
        foreach (var item in queue.ReadReady())
        {
            await api.SubmitObservationAsync(item.Observation, cancellationToken);
            if (TryGetJobId(item.Observation, out var jobId))
            {
                var completed = await api.UpdateJobAsync(
                    jobId,
                    new AgentJobUpdateRequest("completed"),
                    cancellationToken);
                if (completed.Status is "cancelling" or "cancelled")
                {
                    await api.UpdateJobAsync(jobId, new AgentJobUpdateRequest("cancelled"), cancellationToken);
                }
                else
                {
                    status.Set("Online", "Connected to HIOP.", DateTimeOffset.UtcNow, jobId.ToString());
                }
            }

            queue.Acknowledge(item);
        }
    }

    private static bool TryGetJobId(AgentObservation observation, out Guid jobId)
    {
        jobId = Guid.Empty;
        return observation.Payload.ValueKind == System.Text.Json.JsonValueKind.Object &&
            observation.Payload.TryGetProperty("job_id", out var value) &&
            value.ValueKind == System.Text.Json.JsonValueKind.String &&
            Guid.TryParse(value.GetString(), out jobId);
    }
}
