using System.Diagnostics;
using System.Globalization;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Numerics;
using System.IO.Pipes;
using System.Text.RegularExpressions;
using System.Text.Json;
using Hiop.Agent.Core;

namespace Hiop.Agent.Service;

public static partial class AgentJobExecutor
{
    private const int MaximumDiscoveryHosts = 1024;

    public static async Task<(string Source, object Payload)> ExecuteAsync(AgentJob job, CancellationToken cancellationToken)
    {
        return job.Type.ToUpperInvariant() switch
        {
            "DISCOVERY" => ("discovery", await DiscoverAsync(job.Payload, cancellationToken)),
            "PING" or "MONITORING" => ("monitoring", await DiscoverHostAsync(ReadIp(job.Payload, "target"), cancellationToken)),
            "DNS_LOOKUP" => ("dns", await LookupDnsAsync(ReadIp(job.Payload, "target"), cancellationToken)),
            "ARP_SNAPSHOT" => ("arp", await ReadArpSnapshotAsync(cancellationToken)),
            "DEVICE_ACTION" => ("device_action", await ExecuteDeviceActionAsync(job.Payload, cancellationToken)),
            _ => throw new InvalidOperationException($"Unsupported HIOP agent job type '{job.Type}'."),
        };
    }

    private static async Task<object> ExecuteDeviceActionAsync(JsonElement payload, CancellationToken cancellationToken)
    {
        var action = ReadString(payload, "action").ToUpperInvariant();
        if (action is not ("RESTART" or "SHUTDOWN" or "LOCK" or "ENABLE_RDP" or "DISABLE_RDP" or "TRIGGER_WINDOWS_UPDATE"))
        {
            throw new InvalidOperationException("The requested Windows device action is not supported.");
        }

        var result = action == "LOCK"
            ? await RunInteractiveActionAsync(action, cancellationToken)
            : await WindowsPrivilegedActionClient.RunAsync(action, cancellationToken);
        return new
        {
            action,
            succeeded = result.Succeeded,
            message = result.Message,
        };
    }

    private static async Task<AgentDeviceActionResponse> RunInteractiveActionAsync(
        string action,
        CancellationToken cancellationToken)
    {
        try
        {
            using var pipe = new NamedPipeClientStream(
                ".",
                AgentDeviceActionPipe.Name,
                PipeDirection.InOut,
                PipeOptions.Asynchronous);
            await pipe.ConnectAsync(3000, cancellationToken);
            using var reader = new StreamReader(pipe, leaveOpen: true);
            await using var writer = new StreamWriter(pipe, leaveOpen: true) { AutoFlush = true };
            await writer.WriteLineAsync(JsonSerializer.Serialize(new AgentDeviceActionRequest(action), AgentJson.Api).AsMemory(), cancellationToken);
            var response = await reader.ReadLineAsync(cancellationToken);
            return response is null
                ? new AgentDeviceActionResponse(false, "The interactive HIOP Agent tray app returned no action result.")
                : JsonSerializer.Deserialize<AgentDeviceActionResponse>(response, AgentJson.Api)
                    ?? new AgentDeviceActionResponse(false, "The interactive HIOP Agent tray app returned an invalid result.");
        }
        catch (Exception exception) when (exception is IOException or TimeoutException or UnauthorizedAccessException)
        {
            return new AgentDeviceActionResponse(
                false,
                $"Locking requires the interactive HIOP Agent tray app: {exception.Message}");
        }
    }

    private static async Task<object> DiscoverAsync(JsonElement payload, CancellationToken cancellationToken)
    {
        var cidr = ReadString(payload, "cidr");
        var hosts = EnumerateHosts(cidr, MaximumDiscoveryHosts);
        using var concurrency = new SemaphoreSlim(32, 32);
        var tasks = hosts.Select(async host =>
        {
            await concurrency.WaitAsync(cancellationToken);
            try
            {
                return await DiscoverHostAsync(host, cancellationToken);
            }
            finally
            {
                concurrency.Release();
            }
        });

        var results = await Task.WhenAll(tasks);
        var devices = results.Where(result => (bool)result["reachable"]!).ToArray();
        var arpEntries = await ReadArpEntriesAsync(cancellationToken);
        EnrichWithMacAddresses(devices, arpEntries);
        return new Dictionary<string, object?>
        {
            ["network"] = cidr,
            ["devices"] = devices,
            ["scanned"] = hosts.Count,
            ["unresponsive"] = hosts.Count - devices.Length,
            ["agent_computer"] = LocalWindowsInventory.Collect(),
        };
    }

    private static async Task<Dictionary<string, object?>> DiscoverHostAsync(IPAddress target, CancellationToken cancellationToken)
    {
        var result = new Dictionary<string, object?>
        {
            ["target"] = target.ToString(),
            ["reachable"] = false,
            ["latency_ms"] = null,
            ["error"] = "no_response",
            ["reachability_source"] = null,
            ["hostname"] = null,
            ["hostname_source"] = null,
            ["dns_status"] = "unresolved",
        };

        var started = Stopwatch.GetTimestamp();
        try
        {
            using var ping = new Ping();
            var reply = await ping.SendPingAsync(target, TimeSpan.FromSeconds(2)).WaitAsync(cancellationToken);
            if (reply.Status == IPStatus.Success)
            {
                result["reachable"] = true;
                result["latency_ms"] = Math.Round(Stopwatch.GetElapsedTime(started).TotalMilliseconds, 2);
                result["error"] = null;
                result["reachability_source"] = "icmp";
            }
        }
        catch (PingException)
        {
        }
        catch (SocketException)
        {
        }
        catch (TimeoutException)
        {
        }

        if (!(bool)result["reachable"]!)
        {
            foreach (var port in new[] { 443, 80, 445 })
            {
                cancellationToken.ThrowIfCancellationRequested();
                try
                {
                    using var client = new TcpClient(target.AddressFamily);
                    await client.ConnectAsync(target, port, cancellationToken).AsTask().WaitAsync(TimeSpan.FromMilliseconds(500), cancellationToken);
                    result["reachable"] = true;
                    result["error"] = null;
                    result["reachability_source"] = "tcp";
                    result["port"] = port;
                    break;
                }
                catch (Exception exception) when (exception is SocketException or TimeoutException)
                {
                }
            }
        }

        if ((bool)result["reachable"]!)
        {
            var reverse = await ResolveHostnameAsync(target, cancellationToken);
            result["hostname"] = reverse.Hostname;
            result["hostname_source"] = reverse.Hostname is null ? null : "reverse_dns";
            result["dns_status"] = reverse.Status;
        }

        return result;
    }

    private static async Task<object> LookupDnsAsync(IPAddress target, CancellationToken cancellationToken)
    {
        var reverse = await ResolveHostnameAsync(target, cancellationToken);
        return new Dictionary<string, object?>
        {
            ["target"] = target.ToString(),
            ["hostname"] = reverse.Hostname,
            ["error"] = reverse.Hostname is null ? reverse.Status : null,
        };
    }

    private static async Task<(string? Hostname, string Status)> ResolveHostnameAsync(IPAddress target, CancellationToken cancellationToken)
    {
        try
        {
            var entry = await Dns.GetHostEntryAsync(target).WaitAsync(TimeSpan.FromSeconds(2), cancellationToken);
            return (entry.HostName, "ptr_found");
        }
        catch (Exception exception) when (exception is SocketException or TimeoutException)
        {
            return (null, exception.GetType().Name);
        }
    }

    private static async Task<object> ReadArpSnapshotAsync(CancellationToken cancellationToken)
    {
        var entries = await ReadArpEntriesAsync(cancellationToken);
        return new Dictionary<string, object?>
        {
            ["entries"] = entries,
            ["authoritative"] = false,
        };
    }

    private static async Task<List<Dictionary<string, object?>>> ReadArpEntriesAsync(CancellationToken cancellationToken)
    {
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = Path.Combine(Environment.SystemDirectory, "arp.exe"),
                Arguments = "-a",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            },
        };
        if (!process.Start())
        {
            throw new IOException("Windows could not start the built-in ARP table reader.");
        }

        var outputTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        if (process.ExitCode != 0)
        {
            var error = await process.StandardError.ReadToEndAsync(cancellationToken);
            throw new IOException($"The Windows ARP table reader failed: {error}");
        }

        return ArpLineRegex().Matches(await outputTask)
            .Select(match => new Dictionary<string, object?>
            {
                ["ip"] = match.Groups["ip"].Value,
                ["mac"] = match.Groups["mac"].Value.Replace('-', ':').ToLowerInvariant(),
                ["state"] = match.Groups["state"].Value,
            })
            .ToList();
    }

    internal static void EnrichWithMacAddresses(
        IReadOnlyCollection<Dictionary<string, object?>> devices,
        IReadOnlyCollection<Dictionary<string, object?>> arpEntries)
    {
        var macByIp = arpEntries
            .Where(entry => entry.TryGetValue("ip", out var ip) && ip is string &&
                            entry.TryGetValue("mac", out var mac) && LocalWindowsInventory.NormalizeMac(mac?.ToString()) is not null)
            .GroupBy(entry => entry["ip"]!.ToString()!, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                group => group.Key,
                group => LocalWindowsInventory.NormalizeMac(group.First()["mac"]!.ToString())!,
                StringComparer.OrdinalIgnoreCase);

        foreach (var device in devices)
        {
            if (device.TryGetValue("target", out var target) &&
                target is string ip &&
                macByIp.TryGetValue(ip, out var mac))
            {
                device["mac_address"] = mac;
                device["mac_address_source"] = "arp";
            }
        }
    }

    private static IPAddress ReadIp(JsonElement payload, string name)
    {
        var raw = ReadString(payload, name);
        if (!IPAddress.TryParse(raw, out var address))
        {
            throw new FormatException($"The agent job requires a valid IP address in '{name}'.");
        }

        return address;
    }

    private static string ReadString(JsonElement payload, string name)
    {
        if (!payload.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String)
        {
            throw new FormatException($"The agent job is missing the required '{name}' value.");
        }

        var text = value.GetString();
        return string.IsNullOrWhiteSpace(text)
            ? throw new FormatException($"The agent job's '{name}' value is empty.")
            : text;
    }

    internal static List<IPAddress> EnumerateHosts(string cidr, int maximumHosts)
    {
        var parts = cidr.Split('/', StringSplitOptions.TrimEntries);
        if (parts.Length != 2 || !IPAddress.TryParse(parts[0], out var address) ||
            !int.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out var prefix))
        {
            throw new FormatException("The discovery job requires a valid CIDR network.");
        }

        var bytes = address.GetAddressBytes();
        var bits = bytes.Length * 8;
        if (prefix < 0 || prefix > bits)
        {
            throw new FormatException("The discovery network prefix is outside the supported range.");
        }

        var hostBits = bits - prefix;
        var addressValue = new BigInteger(bytes, isUnsigned: true, isBigEndian: true);
        var blockSize = BigInteger.One << hostBits;
        var networkValue = addressValue / blockSize * blockSize;
        var start = networkValue;
        var count = blockSize;
        if (address.AddressFamily == AddressFamily.InterNetwork && prefix < 31)
        {
            start++;
            count -= 2;
        }
        else if (address.AddressFamily == AddressFamily.InterNetworkV6 && prefix < 128)
        {
            start++;
            count--;
        }

        if (count < 1 || count > maximumHosts)
        {
            throw new InvalidOperationException($"Discovery ranges are limited to {maximumHosts} hosts per job.");
        }

        var hosts = new List<IPAddress>((int)count);
        for (var offset = BigInteger.Zero; offset < count; offset++)
        {
            var encoded = (start + offset).ToByteArray(isUnsigned: true, isBigEndian: true);
            if (encoded.Length > bytes.Length)
            {
                throw new InvalidOperationException("The discovery network address is invalid.");
            }

            var host = new byte[bytes.Length];
            encoded.CopyTo(host, host.Length - encoded.Length);
            hosts.Add(new IPAddress(host));
        }

        return hosts;
    }

    [GeneratedRegex(@"(?<ip>\d{1,3}(?:\.\d{1,3}){3})\s+(?<mac>[0-9a-fA-F-]{17})\s+(?<state>\w+)", RegexOptions.CultureInvariant)]
    private static partial Regex ArpLineRegex();
}
