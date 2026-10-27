using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace Hiop.Agent.Core;

public static class WindowsDeviceActionRunner
{
    public static AgentDeviceActionResponse Run(string action)
    {
        if (action == "LOCK")
        {
            return LockWorkStation()
                ? new AgentDeviceActionResponse(true, "The current Windows session was locked.")
                : new AgentDeviceActionResponse(false, "Windows could not lock the current interactive session.");
        }

        if (action is "ENABLE_RDP" or "DISABLE_RDP")
        {
            return ConfigureRemoteDesktop(action == "ENABLE_RDP");
        }

        if (action == "TRIGGER_WINDOWS_UPDATE")
        {
            return StartWindowsUpdateScan();
        }

        var arguments = action switch
        {
            "RESTART" => new[] { "/r", "/t", "60", "/c", "Restart requested by HIOP" },
            "SHUTDOWN" => new[] { "/s", "/t", "60", "/c", "Shutdown requested by HIOP" },
            _ => throw new ArgumentOutOfRangeException(nameof(action), "Unsupported Windows device action."),
        };
        var result = RunUtility(
            Path.Combine(Environment.SystemDirectory, "shutdown.exe"),
            arguments,
            action == "RESTART"
                ? "Windows accepted the restart request and scheduled it in 60 seconds."
                : "Windows accepted the shutdown request and scheduled it in 60 seconds.");
        return result;
    }

    private static AgentDeviceActionResponse ConfigureRemoteDesktop(bool enabled)
    {
        var registryPath = @"SYSTEM\CurrentControlSet\Control\Terminal Server";
        try
        {
            using var key = Registry.LocalMachine.OpenSubKey(registryPath, writable: true)
                ?? throw new InvalidOperationException("The Remote Desktop system setting is unavailable.");
            key.SetValue("fDenyTSConnections", enabled ? 0 : 1, RegistryValueKind.DWord);
            var service = RunUtility(
                "sc.exe",
                enabled ? ["config", "TermService", "start=", "auto"] : ["config", "TermService", "start=", "demand"],
                "Remote Desktop service startup was configured.");
            if (!service.Succeeded)
            {
                return service;
            }

            var firewall = RunUtility(
                "netsh.exe",
                ["advfirewall", "firewall", "set", "rule", "group=remote desktop", "new", $"enable={(enabled ? "yes" : "no")}"],
                "Remote Desktop firewall rules were configured.");
            if (!firewall.Succeeded)
            {
                return firewall;
            }

            if (enabled)
            {
                var start = RunUtility("sc.exe", ["start", "TermService"], "Remote Desktop service was started.");
                if (!start.Succeeded && !start.Message.Contains("already", StringComparison.OrdinalIgnoreCase))
                {
                    return start;
                }
            }

            return new AgentDeviceActionResponse(true, enabled
                ? "Remote Desktop was enabled. Windows Firewall rules were enabled for RDP."
                : "Remote Desktop was disabled and its Windows Firewall rules were disabled.");
        }
        catch (Exception exception) when (
            exception is UnauthorizedAccessException or System.Security.SecurityException or IOException or InvalidOperationException)
        {
            return new AgentDeviceActionResponse(false, exception.Message);
        }
    }

    private static AgentDeviceActionResponse StartWindowsUpdateScan() =>
        RunUtility(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "UsoClient.exe"),
            ["StartScan"],
            "Windows accepted the update scan request. This does not confirm that updates were installed.");

    private static AgentDeviceActionResponse RunUtility(
        string executable,
        IEnumerable<string> arguments,
        string successMessage)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = Path.IsPathRooted(executable) ? executable : Path.Combine(Environment.SystemDirectory, executable),
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
        };
        foreach (var argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        try
        {
            using var process = Process.Start(startInfo)
                ?? throw new InvalidOperationException("Windows could not start the requested system utility.");
            var standardOutput = process.StandardOutput.ReadToEndAsync();
            var standardError = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(30_000))
            {
                if (!process.HasExited)
                {
                    process.Kill(entireProcessTree: true);
                }
                return new AgentDeviceActionResponse(false, "The Windows operation did not finish within 30 seconds.");
            }
            Task.WaitAll(standardOutput, standardError);

            if (process.ExitCode == 0)
            {
                return new AgentDeviceActionResponse(true, successMessage);
            }

            var error = $"{standardError.Result}{Environment.NewLine}{standardOutput.Result}".Trim();
            return new AgentDeviceActionResponse(false, string.IsNullOrWhiteSpace(error)
                ? $"Windows rejected the request (exit code {process.ExitCode})."
                : error);
        }
        catch (Exception exception) when (
            exception is Win32Exception or IOException or InvalidOperationException or UnauthorizedAccessException or AggregateException)
        {
            return new AgentDeviceActionResponse(false, exception.Message);
        }
    }

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool LockWorkStation();
}
