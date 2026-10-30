using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Hiop.Agent.Core;

public static class WindowsPowerPolicy
{
    private static readonly HashSet<string> UnsavedWorkProcesses = new(StringComparer.OrdinalIgnoreCase)
    {
        "atom",
        "brave",
        "chrome",
        "code",
        "devenv",
        "excel",
        "firefox",
        "msedge",
        "mspub",
        "notepad",
        "notepad++",
        "obsidian",
        "onenote",
        "onenoteim",
        "opera",
        "outlook",
        "powerpnt",
        "scalc",
        "simpress",
        "soffice",
        "sublime_text",
        "visio",
        "vivaldi",
        "winword",
        "wordpad",
    };

    private static readonly HashSet<string> SystemWindowProcesses = new(StringComparer.OrdinalIgnoreCase)
    {
        "dwm",
        "searchhost",
        "searchindexer",
        "services",
        "shellexperiencehost",
        "startmenuexperiencehost",
        "svchost",
        "system",
        "textinputhost",
        "wininit",
        "winlogon",
    };

    public static TimeSpan? GetIdleDuration()
    {
        var information = new LastInputInfo
        {
            Size = (uint)Marshal.SizeOf<LastInputInfo>(),
        };
        if (!GetLastInputInfo(ref information))
        {
            return null;
        }

        var elapsedMilliseconds = unchecked((uint)Environment.TickCount - information.Time);
        return TimeSpan.FromMilliseconds(elapsedMilliseconds);
    }

    public static IReadOnlyList<string>? GetOpenApplicationWindows()
    {
        var blockers = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            var currentProcessId = Environment.ProcessId;
            foreach (var process in Process.GetProcesses())
            {
                using (process)
                {
                    if (process.Id == currentProcessId)
                    {
                        continue;
                    }

                    var name = process.ProcessName;
                    var hasVisibleWindow = UnsavedWorkProcesses.Contains(name)
                        ? false
                        : process.MainWindowHandle != IntPtr.Zero;
                    if (IsPotentialUnsavedWork(name, hasVisibleWindow))
                    {
                        blockers.Add(name);
                    }
                }
            }
        }
        catch (Win32Exception)
        {
            return null;
        }
        catch (InvalidOperationException)
        {
            return null;
        }
        catch (NotSupportedException)
        {
            return null;
        }

        return blockers.Order(StringComparer.OrdinalIgnoreCase).ToArray();
    }

    public static bool CanAutomaticallyShutDown(TimeSpan? idleDuration, IReadOnlyCollection<string>? openApplications) =>
        idleDuration >= TimeSpan.FromSeconds(60) && openApplications is { Count: 0 };

    public static bool IsPotentialUnsavedWork(string processName, bool hasVisibleWindow) =>
        UnsavedWorkProcesses.Contains(processName) ||
        hasVisibleWindow && !SystemWindowProcesses.Contains(processName);

    public static bool TryLockWorkstation(out int error)
    {
        var locked = LockWorkStation();
        error = locked ? 0 : Marshal.GetLastWin32Error();
        return locked;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LastInputInfo
    {
        public uint Size;
        public uint Time;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool GetLastInputInfo(ref LastInputInfo information);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool LockWorkStation();
}
