using System.Diagnostics;
using System.Diagnostics.Eventing.Reader;
using System.Globalization;
using System.Management;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using Microsoft.CSharp.RuntimeBinder;
using Microsoft.Win32;

namespace Hiop.Agent.Core;

public sealed record WindowsHealthSnapshot(
    bool? FastStartupEnabled,
    string? LidCloseAction,
    double? BatteryHealthPercent,
    int? PendingWindowsUpdates,
    DateTimeOffset? LastShutdownAt);

public static class WindowsHealthReader
{
    private static readonly object Gate = new();
    private static WindowsHealthSnapshot? _snapshot;
    private static DateTimeOffset _collectedAt;
    private static DateTimeOffset _nextPendingWindowsUpdateReadAt;
    private static Task<int?>? _pendingWindowsUpdateTask;

    public static WindowsHealthSnapshot Collect()
    {
        lock (Gate)
        {
            if (_snapshot is not null && DateTimeOffset.UtcNow - _collectedAt < TimeSpan.FromMinutes(15))
            {
                var pendingUpdates = ReadPendingWindowsUpdates();
                if (pendingUpdates.HasValue)
                {
                    _snapshot = _snapshot with { PendingWindowsUpdates = pendingUpdates };
                }

                return _snapshot;
            }

            _snapshot = new(
                ReadFastStartupEnabled(),
                ReadLidCloseAction(),
                ReadBatteryHealthPercent(),
                ReadPendingWindowsUpdates(),
                ReadLastShutdownAt());
            _collectedAt = DateTimeOffset.UtcNow;
            return _snapshot;
        }
    }

    private static bool? ReadFastStartupEnabled()
    {
        try
        {
            using var key = Registry.LocalMachine.OpenSubKey(
                @"SYSTEM\CurrentControlSet\Control\Session Manager\Power");
            return key?.GetValue("HiberbootEnabled") is int enabled ? enabled == 1 : null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
        catch (System.Security.SecurityException)
        {
            return null;
        }
    }

    private static string? ReadLidCloseAction()
    {
        try
        {
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = Path.Combine(Environment.SystemDirectory, "powercfg.exe"),
                Arguments = "/query SCHEME_CURRENT SUB_BUTTONS LIDACTION",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            });
            if (process is null)
            {
                return null;
            }

            var outputTask = process.StandardOutput.ReadToEndAsync();
            var errorTask = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(5000))
            {
                process.Kill(entireProcessTree: true);
                return null;
            }

            var output = outputTask.GetAwaiter().GetResult();
            _ = errorTask.GetAwaiter().GetResult();
            if (process.ExitCode != 0)
            {
                return null;
            }

            var values = Regex.Matches(
                    output,
                    @"Current (AC|DC) Power Setting Index:\s*0x([0-9a-f]+)",
                    RegexOptions.IgnoreCase)
                .Cast<Match>()
                .ToDictionary(
                    match => match.Groups[1].Value.ToUpperInvariant(),
                    match => match.Groups[2].Value,
                    StringComparer.Ordinal);
            if (values.Count == 0)
            {
                return null;
            }

            var ac = values.TryGetValue("AC", out var acValue) ? FormatLidAction(acValue) : null;
            var dc = values.TryGetValue("DC", out var dcValue) ? FormatLidAction(dcValue) : null;
            return ac is not null && dc is not null ? $"AC {ac} / DC {dc}" : ac ?? dc;
        }
        catch (InvalidOperationException)
        {
            return null;
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return null;
        }
        catch (IOException)
        {
            return null;
        }
    }

    private static string? FormatLidAction(string value)
    {
        if (!int.TryParse(value, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var action))
        {
            return null;
        }

        return action switch
        {
            0 => "Do nothing",
            1 => "Sleep",
            2 => "Hibernate",
            3 => "Shut down",
            _ => $"Unknown ({action})",
        };
    }

    private static double? ReadBatteryHealthPercent()
    {
        try
        {
            var fullCapacity = SumWmiValues("BatteryFullChargedCapacity", "FullChargedCapacity");
            var designCapacity = SumWmiValues("BatteryStaticData", "DesignedCapacity");
            if (fullCapacity is not > 0 || designCapacity is not > 0)
            {
                return null;
            }

            return Math.Clamp(fullCapacity * 100d / designCapacity, 0, 100);
        }
        catch (ManagementException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    private static long SumWmiValues(string className, string property)
    {
        using var searcher = new ManagementObjectSearcher(
            new ManagementScope(@"\\.\root\wmi"),
            new ObjectQuery($"SELECT {property} FROM {className}"));
        using var results = searcher.Get();
        return results.Cast<ManagementObject>()
            .Select(item => long.TryParse(item[property]?.ToString(), out var value) ? value : 0)
            .Sum();
    }

    private static int? ReadPendingWindowsUpdates()
    {
        if (_pendingWindowsUpdateTask is null)
        {
            if (DateTimeOffset.UtcNow < _nextPendingWindowsUpdateReadAt)
            {
                return null;
            }

            _nextPendingWindowsUpdateReadAt = DateTimeOffset.UtcNow.AddMinutes(15);
            _pendingWindowsUpdateTask = Task.Run(ReadPendingWindowsUpdatesCore);
            return null;
        }

        if (!_pendingWindowsUpdateTask.IsCompleted)
        {
            return null;
        }

        var completed = _pendingWindowsUpdateTask;
        _pendingWindowsUpdateTask = null;
        if (completed.IsCompletedSuccessfully)
        {
            return completed.Result;
        }

        Debug.WriteLine($"HIOP could not read pending Windows updates: {completed.Exception?.GetBaseException().Message ?? "The background lookup was canceled."}");
        return null;
    }

    private static int? ReadPendingWindowsUpdatesCore()
    {
        object? session = null;
        object? searcher = null;
        object? result = null;
        object? updates = null;
        try
        {
            var sessionType = Type.GetTypeFromProgID("Microsoft.Update.Session", throwOnError: false);
            if (sessionType is null)
            {
                return null;
            }

            session = Activator.CreateInstance(sessionType);
            if (session is null)
            {
                return null;
            }

            dynamic updateSession = session;
            searcher = updateSession.CreateUpdateSearcher();
            dynamic updateSearcher = searcher;
            result = updateSearcher.Search("IsInstalled=0 and IsHidden=0");
            dynamic searchResult = result;
            updates = searchResult.Updates;
            dynamic updateCollection = updates;
            return Convert.ToInt32(updateCollection.Count, CultureInfo.InvariantCulture);
        }
        catch (COMException)
        {
            return null;
        }
        catch (InvalidComObjectException)
        {
            return null;
        }
        catch (InvalidCastException)
        {
            return null;
        }
        catch (RuntimeBinderException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
        finally
        {
            foreach (var value in new[] { updates, result, searcher, session })
            {
                if (value is not null && Marshal.IsComObject(value))
                {
                    Marshal.FinalReleaseComObject(value);
                }
            }
        }
    }

    private static DateTimeOffset? ReadLastShutdownAt()
    {
        try
        {
            var query = new EventLogQuery(
                "System",
                PathType.LogName,
                "*[System[(EventID=41 or EventID=1074 or EventID=6006 or EventID=6008)]]")
            {
                ReverseDirection = true,
            };
            using var reader = new EventLogReader(query);
            using var record = reader.ReadEvent();
            return record?.TimeCreated is DateTime eventTime
                ? new DateTimeOffset(eventTime).ToUniversalTime()
                : null;
        }
        catch (EventLogException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }
}
