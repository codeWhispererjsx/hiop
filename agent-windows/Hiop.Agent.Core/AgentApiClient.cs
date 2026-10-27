using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Management;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.IO;

namespace Hiop.Agent.Core;

public sealed class AgentApiException(HttpStatusCode statusCode, string message)
    : HttpRequestException(message, null, statusCode);

public sealed class AgentApiClient : IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = AgentJson.Api;
    private readonly HttpClient _httpClient;
    private readonly string _apiRoot;
    private readonly AgentCredentialStore _credentials;

    public AgentApiClient(AgentConfiguration configuration, AgentCredentialStore credentials)
    {
        configuration.Validate();
        _apiRoot = configuration.BackendUrl.TrimEnd('/') + "/api/v1";
        _credentials = credentials;
        _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(20),
        };
        _httpClient.DefaultRequestHeaders.UserAgent.ParseAdd($"HIOP-Agent/{AgentConfiguration.Version}");
    }

    public async Task<AgentEnrollmentResponse> EnrollAsync(string token, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new ArgumentException("The one-time enrollment token is required.", nameof(token));
        }

        var request = new AgentEnrollmentRequest(token, Environment.MachineName, AgentConfiguration.Version);
        return await SendAsync<AgentEnrollmentResponse>(
            HttpMethod.Post,
            "/agent/enroll",
            request,
            authenticated: false,
            cancellationToken);
    }

    public Task<AgentHeartbeatResponse> SendHeartbeatAsync(
        int pendingQueue,
        string? lastSuccessfulJob,
        CancellationToken cancellationToken)
    {
        var operatingSystem = ReadWmiValue("Win32_OperatingSystem", "Caption");
        var memoryTotalKilobytes = ReadWmiValue("Win32_OperatingSystem", "TotalVisibleMemorySize");
        var memoryFreeKilobytes = ReadWmiValue("Win32_OperatingSystem", "FreePhysicalMemory");
        var cpu = ReadWmiValue("Win32_PerfFormattedData_PerfOS_Processor", "PercentProcessorTime", "Name='_Total'");
        var loggedUser = ReadWmiValue("Win32_ComputerSystem", "UserName");
        var lastUpdate = ReadLatestWindowsUpdate();
        var diskFree = DriveInfo.GetDrives().Where(drive => drive.IsReady && drive.DriveType == DriveType.Fixed)
            .Select(drive => drive.AvailableFreeSpace).DefaultIfEmpty().Sum();
        var ipAddress = NetworkInterface.GetAllNetworkInterfaces()
            .Where(adapter => adapter.OperationalStatus == OperationalStatus.Up && adapter.NetworkInterfaceType is not NetworkInterfaceType.Loopback and not NetworkInterfaceType.Tunnel)
            .SelectMany(adapter => adapter.GetIPProperties().UnicastAddresses)
            .Select(address => address.Address)
            .FirstOrDefault(address => address.AddressFamily == AddressFamily.InterNetwork && !IPAddress.IsLoopback(address))
            ?.ToString();
        var request = new AgentHeartbeatRequest(
            AgentConfiguration.Version,
            Environment.MachineName,
            Math.Max(0, Environment.TickCount64 / 1000),
            pendingQueue,
            10000,
            lastSuccessfulJob,
            ParseDouble(cpu),
            ParseLong(memoryTotalKilobytes) is long totalMemory ? totalMemory * 1024 : null,
            ParseLong(memoryFreeKilobytes) is long freeMemory ? freeMemory * 1024 : null,
            diskFree,
            ipAddress,
            operatingSystem,
            loggedUser,
            lastUpdate);
        return SendAsync<AgentHeartbeatResponse>(HttpMethod.Post, "/agent/heartbeat", request, true, cancellationToken);
    }

    public Task<List<AgentJob>> GetJobsAsync(CancellationToken cancellationToken) =>
        SendAsync<List<AgentJob>>(HttpMethod.Get, "/agent/jobs", null, true, cancellationToken);

    public Task<AgentJobStatusResponse> GetJobStatusAsync(Guid id, CancellationToken cancellationToken) =>
        SendAsync<AgentJobStatusResponse>(HttpMethod.Get, $"/agent/jobs/{id}", null, true, cancellationToken);

    public Task<AgentJobStatusResponse> UpdateJobAsync(Guid id, AgentJobUpdateRequest request, CancellationToken cancellationToken) =>
        SendAsync<AgentJobStatusResponse>(HttpMethod.Post, $"/agent/jobs/{id}", request, true, cancellationToken);

    public async Task SubmitObservationAsync(AgentObservation observation, CancellationToken cancellationToken)
    {
        await SendAsync<JsonElement>(HttpMethod.Post, "/agent/observations", observation, true, cancellationToken);
    }

    private async Task<T> SendAsync<T>(
        HttpMethod method,
        string path,
        object? body,
        bool authenticated,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(method, _apiRoot + path);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (authenticated)
        {
            var credential = _credentials.Load()
                ?? throw new InvalidOperationException("The HIOP agent is not enrolled.");
            request.Headers.Authorization = new AuthenticationHeaderValue("Agent", credential);
        }

        if (body is not null)
        {
            request.Content = JsonContent.Create(body, options: JsonOptions);
        }

        using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            var detail = await response.Content.ReadAsStringAsync(cancellationToken);
            throw new AgentApiException(
                response.StatusCode,
                $"HIOP agent API returned {(int)response.StatusCode}: {detail}");
        }

        if (response.Content.Headers.ContentLength == 0)
        {
            return JsonSerializer.Deserialize<T>("{}", JsonOptions)
                ?? throw new InvalidDataException("The HIOP agent API returned an empty response.");
        }

        return await response.Content.ReadFromJsonAsync<T>(JsonOptions, cancellationToken)
            ?? throw new InvalidDataException("The HIOP agent API returned an empty response.");
    }

    public void Dispose() => _httpClient.Dispose();

    private static string? ReadWmiValue(string className, string property, string? filter = null)
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(
                $"SELECT {property} FROM {className}" + (filter is null ? string.Empty : $" WHERE {filter}"));
            using var results = searcher.Get();
            return results.Cast<ManagementObject>().FirstOrDefault()?[property]?.ToString();
        }
        catch (ManagementException)
        {
            return null;
        }
    }

    private static DateTimeOffset? ReadLatestWindowsUpdate()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT InstalledOn FROM Win32_QuickFixEngineering");
            using var results = searcher.Get();
            var dates = results.Cast<ManagementObject>()
                .Select(item => DateTime.TryParse(item["InstalledOn"]?.ToString(), out var date) ? date : (DateTime?)null)
                .Where(date => date.HasValue)
                .Select(date => date!.Value)
                .ToArray();
            return dates.Length == 0 ? null : new DateTimeOffset(dates.Max().ToUniversalTime());
        }
        catch (ManagementException)
        {
            return null;
        }
    }

    private static long? ParseLong(string? value) => long.TryParse(value, out var parsed) ? parsed : null;
    private static double? ParseDouble(string? value) => double.TryParse(value, out var parsed) ? Math.Clamp(parsed, 0, 100) : null;
}
