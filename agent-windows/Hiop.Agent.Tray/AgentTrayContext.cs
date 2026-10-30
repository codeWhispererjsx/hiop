using System.Diagnostics;
using Hiop.Agent.Core;

namespace Hiop.Agent.Tray;

internal sealed class AgentTrayContext : ApplicationContext
{
    private readonly NotifyIcon _icon;
    private readonly ToolStripMenuItem _statusItem;
    private readonly System.Windows.Forms.Timer _refreshTimer;
    private readonly string _configPath = AgentConfiguration.DefaultPath;
    private readonly AgentPowerEventQueue _powerEvents = new(
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HIOP", "Agent"));
    private AgentConfiguration? _configuration;
    private readonly ToolStripMenuItem _enrollItem;
    private EndOfDayPromptForm? _endOfDayPrompt;
    private bool _refreshing;
    private bool _smartLockArmed = true;
    private bool _powerStorageErrorShown;

    public AgentTrayContext()
    {
        _statusItem = new ToolStripMenuItem("Checking HIOP Agent...") { Enabled = false };
        var menu = new ContextMenuStrip();
        menu.Items.Add(_statusItem);
        menu.Items.Add(new ToolStripSeparator());
        _enrollItem = new ToolStripMenuItem("Connect or enroll...", null, async (_, _) => await EnrollAsync());
        menu.Items.Add(_enrollItem);
        menu.Items.Add("Open HIOP", null, (_, _) => OpenHiop());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Exit", null, (_, _) => ConfirmExit());

        _icon = new NotifyIcon
        {
            Icon = SystemIcons.Information,
            Text = "HIOP Agent: checking status",
            ContextMenuStrip = menu,
            Visible = true,
        };
        _icon.DoubleClick += async (_, _) => await RefreshStatusAsync();

        _refreshTimer = new System.Windows.Forms.Timer { Interval = 10000 };
        _refreshTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _refreshTimer.Start();
        _ = RefreshStatusAsync();
    }

    private async Task RefreshStatusAsync()
    {
        if (_refreshing)
        {
            return;
        }

        _refreshing = true;
        try
        {
            var response = await AgentControlClient.SendAsync(new AgentControlRequest("status"));
            _statusItem.Text = $"Status: {response.Status}";
            _icon.Text = $"HIOP Agent: {response.Status}";
            // Enrolled computers must be revoked in HIOP before they can enroll again.
            _enrollItem.Enabled = !response.Enrolled;
            if (response.Enrolled)
            {
                await ApplySmartLockPolicyAsync(response.SmartLockTimeoutSeconds);
                await FlushPowerEventsAsync();
                await ShowAdminNoticesAsync();
            }
        }
        catch (Exception exception) when (exception is IOException or TimeoutException or UnauthorizedAccessException)
        {
            _statusItem.Text = "Status: Service not running. Restart the computer or contact IT.";
            _icon.Text = "HIOP Agent: service not running";
        }
        finally
        {
            CheckEndOfDayPolicy();
            _refreshing = false;
        }
    }

    private async Task ApplySmartLockPolicyAsync(int? timeoutSeconds)
    {
        if (timeoutSeconds != 300)
        {
            return;
        }

        var idleDuration = WindowsPowerPolicy.GetIdleDuration();
        if (idleDuration is null)
        {
            Debug.WriteLine("HIOP smart lock was skipped because Windows could not report idle time.");
            return;
        }

        if (idleDuration < TimeSpan.FromSeconds(timeoutSeconds.Value))
        {
            _smartLockArmed = true;
            return;
        }

        if (!_smartLockArmed)
        {
            return;
        }

        _powerEvents.QueueEvent("SMART_LOCK_REQUESTED");
        if (WindowsPowerPolicy.TryLockWorkstation(out var error))
        {
            _smartLockArmed = false;
            _powerEvents.QueueEvent("SMART_LOCK_APPLIED");
            await FlushPowerEventsAsync();
            return;
        }

        _smartLockArmed = false;
        _powerEvents.QueueEvent("SMART_LOCK_FAILED", $"Smart Lock could not be applied (Windows error {error}).");
        Debug.WriteLine($"HIOP Smart Lock failed with Windows error {error}.");
        await FlushPowerEventsAsync();
    }

    private async Task FlushPowerEventsAsync()
    {
        foreach (var powerEvent in _powerEvents.PendingEvents)
        {
            try
            {
                var response = await AgentControlClient.SendAsync(
                    new AgentControlRequest("report-power-event", PowerEvent: powerEvent));
                if (!response.Ok)
                {
                    Debug.WriteLine($"HIOP power event {powerEvent.EventId} is waiting for server delivery.");
                    return;
                }

                _powerEvents.Acknowledge(powerEvent.EventId);
            }
            catch (Exception exception) when (exception is IOException or TimeoutException or UnauthorizedAccessException)
            {
                Debug.WriteLine($"HIOP power event {powerEvent.EventId} could not be delivered: {exception.Message}");
                return;
            }
        }
    }

    private void CheckEndOfDayPolicy()
    {
        try
        {
            var now = DateTime.Now;
            var localDate = DateOnly.FromDateTime(now);
            if (now.TimeOfDay >= new TimeSpan(22, 45, 0) && now.TimeOfDay < new TimeSpan(23, 30, 0) &&
                _powerEvents.QueueDailyEvent("END_OF_DAY_NUDGE", localDate, isPrompt: false))
            {
                _icon.BalloonTipTitle = "HIOP: closing time reminder";
                _icon.BalloonTipText = "Closing time is approaching. Please save your work and shut down when ready.";
                _icon.BalloonTipIcon = ToolTipIcon.Info;
                _icon.ShowBalloonTip(10000);
            }

            if (now.TimeOfDay < new TimeSpan(23, 30, 0) || _endOfDayPrompt is not null)
            {
                return;
            }

            var idleDuration = WindowsPowerPolicy.GetIdleDuration();
            if (idleDuration is null || idleDuration < TimeSpan.FromMinutes(30) ||
                !_powerEvents.QueueDailyEvent("END_OF_DAY_PROMPT", localDate, isPrompt: true))
            {
                return;
            }

            _endOfDayPrompt = new EndOfDayPromptForm(
                RequestLocalShutdown,
                reason => _powerEvents.QueueEvent("END_OF_DAY_STAY_ON", reason),
                reason => _powerEvents.QueueEvent("END_OF_DAY_SHUTDOWN_BLOCKED", reason));
            _endOfDayPrompt.FormClosed += (_, _) => _endOfDayPrompt = null;
            _endOfDayPrompt.Show();
        }
        catch (IOException exception)
        {
            ShowPowerStorageError(exception.Message);
        }
        catch (UnauthorizedAccessException exception)
        {
            ShowPowerStorageError(exception.Message);
        }
    }

    private void ShowPowerStorageError(string message)
    {
        Debug.WriteLine($"HIOP end-of-day policy is disabled because its audit state could not be saved: {message}");
        if (_powerStorageErrorShown)
        {
            return;
        }

        _powerStorageErrorShown = true;
        _icon.BalloonTipTitle = "HIOP power policy paused";
        _icon.BalloonTipText = "HIOP could not save its local audit state. Automatic power actions are paused.";
        _icon.BalloonTipIcon = ToolTipIcon.Error;
        _icon.ShowBalloonTip(10000);
    }

    private bool RequestLocalShutdown()
    {
        _powerEvents.QueueEvent("END_OF_DAY_SHUTDOWN_REQUESTED");
        try
        {
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = Path.Combine(Environment.SystemDirectory, "shutdown.exe"),
                UseShellExecute = false,
                CreateNoWindow = true,
                ArgumentList = { "/s", "/t", "0" },
            });
            if (process is null)
            {
                _powerEvents.QueueEvent("END_OF_DAY_SHUTDOWN_BLOCKED", "Windows did not start the normal shutdown process.");
                return false;
            }

            _ = FlushPowerEventsAsync();
            return true;
        }
        catch (System.ComponentModel.Win32Exception exception)
        {
            _powerEvents.QueueEvent("END_OF_DAY_SHUTDOWN_BLOCKED", $"Windows rejected the normal shutdown request: {exception.Message[..Math.Min(exception.Message.Length, 200)]}");
            return false;
        }
        catch (InvalidOperationException exception)
        {
            _powerEvents.QueueEvent("END_OF_DAY_SHUTDOWN_BLOCKED", $"Windows rejected the normal shutdown request: {exception.Message[..Math.Min(exception.Message.Length, 200)]}");
            return false;
        }
        catch (IOException exception)
        {
            _powerEvents.QueueEvent("END_OF_DAY_SHUTDOWN_BLOCKED", $"Windows rejected the normal shutdown request: {exception.Message[..Math.Min(exception.Message.Length, 200)]}");
            return false;
        }
    }

    private async Task ShowAdminNoticesAsync()
    {
        try
        {
            var response = await AgentControlClient.SendAsync(new AgentControlRequest("notices"));
            if (!response.Ok || response.Notices is null)
            {
                return;
            }


            foreach (var notice in response.Notices)
            {
                _icon.BalloonTipTitle = "HIOP IT Notice";
                _icon.BalloonTipText = notice.Message;
                _icon.BalloonTipIcon = ToolTipIcon.Info;
                _icon.ShowBalloonTip(10000);
                var acknowledgement = await AgentControlClient.SendAsync(
                    new AgentControlRequest("acknowledge-notice", NoticeId: notice.Id));
                if (!acknowledgement.Ok)
                {
                    Debug.WriteLine($"HIOP admin notice {notice.Id} could not be acknowledged.");
                }
                break;
            }
        }
        catch (Exception exception) when (exception is IOException or TimeoutException or UnauthorizedAccessException)
        {
            Debug.WriteLine($"HIOP admin notice delivery failed: {exception.Message}");
        }
    }

    private async Task EnrollAsync()
    {
        using var dialog = new EnrollmentDialog();
        if (dialog.ShowDialog() != DialogResult.OK)
        {
            return;
        }

        try
        {
            var response = await AgentControlClient.SendAsync(
                new AgentControlRequest("enroll", dialog.EnrollmentToken));
            MessageBox.Show(
                response.Message,
                response.Ok ? "HIOP Agent" : "Enrollment failed",
                MessageBoxButtons.OK,
                response.Ok ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
            await RefreshStatusAsync();
        }
        catch (Exception exception) when (exception is IOException or TimeoutException or UnauthorizedAccessException)
        {
            MessageBox.Show(
                $"Could not contact the HIOP agent service: {exception.Message}",
                "HIOP Agent",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private void ConfirmExit()
    {
        var answer = MessageBox.Show(
            "Closing HIOP Agent stops IT notices, end-of-day reminders, and the idle screen lock on this computer until you sign in again.\n\nClose HIOP Agent anyway?",
            "HIOP Agent",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Warning,
            MessageBoxDefaultButton.Button2);
        if (answer == DialogResult.Yes)
        {
            ExitThread();
        }
    }

    private void OpenHiop()
    {
        try
        {
            _configuration ??= AgentConfiguration.Load(_configPath);
            Process.Start(new ProcessStartInfo(_configuration.BackendUrl) { UseShellExecute = true });
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            MessageBox.Show(exception.Message, "HIOP Agent", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    protected override void ExitThreadCore()
    {
        _refreshTimer.Stop();
        _refreshTimer.Dispose();
        _icon.Visible = false;
        _icon.Dispose();
        base.ExitThreadCore();
    }
}
