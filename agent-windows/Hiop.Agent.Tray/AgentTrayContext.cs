using System.Diagnostics;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;
using Hiop.Agent.Core;

namespace Hiop.Agent.Tray;

internal sealed class AgentTrayContext : ApplicationContext
{
    private readonly NotifyIcon _icon;
    private readonly ToolStripMenuItem _statusItem;
    private readonly System.Windows.Forms.Timer _refreshTimer;
    private readonly CancellationTokenSource _actionListenerCancellation = new();
    private readonly string _configPath = AgentConfiguration.DefaultPath;
    private AgentConfiguration? _configuration;
    private bool _refreshing;

    public AgentTrayContext()
    {
        _statusItem = new ToolStripMenuItem("Checking HIOP Agent...") { Enabled = false };
        var menu = new ContextMenuStrip();
        menu.Items.Add(_statusItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Connect or enroll...", null, async (_, _) => await EnrollAsync());
        menu.Items.Add("Open HIOP", null, (_, _) => OpenHiop());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Exit", null, (_, _) => ExitThread());

        _icon = new NotifyIcon
        {
            Icon = SystemIcons.Information,
            Text = "HIOP Protected - IT Support Active",
            ContextMenuStrip = menu,
            Visible = true,
        };
        _icon.DoubleClick += async (_, _) => await RefreshStatusAsync();

        _refreshTimer = new System.Windows.Forms.Timer { Interval = 10000 };
        _refreshTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _refreshTimer.Start();
        _ = ListenForDeviceActionsAsync(_actionListenerCancellation.Token);
        _ = RefreshStatusAsync();
    }

    private static NamedPipeServerStream CreateDeviceActionPipe()
    {
        var security = new PipeSecurity();
        var agentService = (SecurityIdentifier)new NTAccount(@"NT SERVICE\HIOPAgent")
            .Translate(typeof(SecurityIdentifier));
        security.AddAccessRule(new PipeAccessRule(agentService, PipeAccessRights.ReadWrite, AccessControlType.Allow));
        return NamedPipeServerStreamAcl.Create(
            AgentDeviceActionPipe.Name,
            PipeDirection.InOut,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous,
            1024,
            1024,
            security);
    }

    private async Task ListenForDeviceActionsAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await using var pipe = CreateDeviceActionPipe();
                await pipe.WaitForConnectionAsync(cancellationToken);
                using var reader = new StreamReader(pipe, leaveOpen: true);
                await using var writer = new StreamWriter(pipe, leaveOpen: true) { AutoFlush = true };
                var line = await reader.ReadLineAsync(cancellationToken);
                var request = line is null
                    ? null
                    : JsonSerializer.Deserialize<AgentDeviceActionRequest>(line, AgentJson.Api);
                var response = request?.Action == "LOCK"
                    ? WindowsDeviceActionRunner.Run(request.Action)
                    : new AgentDeviceActionResponse(false, "Only interactive session locking is allowed on this pipe.");
                await writer.WriteLineAsync(JsonSerializer.Serialize(response, AgentJson.Api).AsMemory(), cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                break;
            }
            catch (IOException exception)
            {
                Debug.WriteLine($"HIOP agent action pipe failed: {exception.Message}");
                await DelayBeforeRetryAsync(cancellationToken);
            }
            catch (UnauthorizedAccessException exception)
            {
                Debug.WriteLine($"HIOP agent action pipe access failed: {exception.Message}");
                await DelayBeforeRetryAsync(cancellationToken);
            }
            catch (JsonException exception)
            {
                Debug.WriteLine($"HIOP agent action request was invalid: {exception.Message}");
            }
        }
    }

    private static async Task DelayBeforeRetryAsync(CancellationToken cancellationToken)
    {
        try
        {
            await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
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
        }
        catch (Exception exception) when (exception is IOException or TimeoutException or UnauthorizedAccessException)
        {
            _statusItem.Text = "Status: Service unavailable";
            _icon.Text = "HIOP Agent: Service unavailable";
        }
        finally
        {
            _refreshing = false;
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
        _actionListenerCancellation.Cancel();
        _actionListenerCancellation.Dispose();
        _refreshTimer.Stop();
        _refreshTimer.Dispose();
        _icon.Visible = false;
        _icon.Dispose();
        base.ExitThreadCore();
    }
}
