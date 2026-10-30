using System.Globalization;
using Hiop.Agent.Core;

namespace Hiop.Agent.Tray;

internal sealed class EndOfDayPromptForm : Form
{
    private readonly Func<bool> _requestShutdown;
    private readonly Action<string> _stayOn;
    private readonly Action<string> _logBlocked;
    private readonly Label _countdownLabel;
    private readonly Label _safetyLabel;
    private readonly TextBox _reasonInput;
    private readonly Button _stayOnButton;
    private readonly System.Windows.Forms.Timer _timer;
    private int _secondsRemaining = 60;
    private bool _allowClose;
    private bool _blockRecorded;
    private bool _auditFailed;

    public EndOfDayPromptForm(Func<bool> requestShutdown, Action<string> stayOn, Action<string> logBlocked)
    {
        _requestShutdown = requestShutdown;
        _stayOn = stayOn;
        _logBlocked = logBlocked;
        // Layout below is in 96-DPI pixels; scale it with the display so text is not clipped at 125%+.
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        Text = "HIOP End-of-Day Reminder";
        Width = 520;
        Height = 350;
        MinimizeBox = false;
        MaximizeBox = false;
        ControlBox = false;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterScreen;
        TopMost = true;

        var heading = new Label
        {
            Text = "Closing time — please save your work.",
            Font = new Font(Font, FontStyle.Bold),
            AutoSize = true,
            Left = 24,
            Top = 22,
        };
        var explanation = new Label
        {
            Text = "If this computer stays idle for 60 more seconds, HIOP will ask Windows to shut down normally. Open work apps or windows pause the countdown, and HIOP never force-closes anything.",
            AutoSize = false,
            Left = 24,
            Top = 56,
            Width = 455,
            Height = 70,
        };
        _safetyLabel = new Label
        {
            AutoSize = false,
            Left = 24,
            Top = 136,
            Width = 455,
            Height = 44,
            ForeColor = Color.DarkRed,
        };
        _countdownLabel = new Label
        {
            AutoSize = true,
            Left = 24,
            Top = 183,
            Font = new Font(Font.FontFamily, 12, FontStyle.Bold),
        };
        var reasonLabel = new Label
        {
            Text = "Need this computer to stay on? Tell IT why (at least 5 characters):",
            AutoSize = true,
            Left = 24,
            Top = 219,
        };
        _reasonInput = new TextBox
        {
            Left = 24,
            Top = 242,
            Width = 455,
            MaxLength = 250,
        };
        _stayOnButton = new Button
        {
            Text = "Keep computer on",
            Left = 319,
            Top = 278,
            Width = 160,
            Enabled = false,
        };
        _stayOnButton.Click += OnStayOn;
        _reasonInput.TextChanged += (_, _) => _stayOnButton.Enabled = _reasonInput.Text.Trim().Length >= 5;
        AcceptButton = _stayOnButton;
        Controls.AddRange([heading, explanation, _safetyLabel, _countdownLabel, reasonLabel, _reasonInput, _stayOnButton]);

        _timer = new System.Windows.Forms.Timer { Interval = 1000 };
        _timer.Tick += OnTimerTick;
        FormClosing += OnFormClosing;
        UpdateCountdownLabel();
        _timer.Start();
    }

    private void OnTimerTick(object? sender, EventArgs eventArgs)
    {
        var idleDuration = WindowsPowerPolicy.GetIdleDuration();
        var openApplications = WindowsPowerPolicy.GetOpenApplicationWindows();
        if (idleDuration is null || openApplications is null)
        {
            _secondsRemaining = 60;
            RecordBlocked("Windows could not verify idle time or running work applications.");
            _safetyLabel.Text = "Automatic shutdown is paused because HIOP could not verify device activity and open applications.";
            UpdateCountdownLabel();
            return;
        }

        if (openApplications.Count > 0)
        {
            _secondsRemaining = 60;
            RecordBlocked("A known work app or visible application window was detected; automatic shutdown is paused to protect possible unsaved work.");
            var applicationNames = string.Join(", ", openApplications.Take(4));
            _safetyLabel.Text = $"Automatic shutdown is paused while work apps or application windows are open: {applicationNames}.";
            UpdateCountdownLabel();
            return;
        }

        _safetyLabel.Text = idleDuration < TimeSpan.FromSeconds(60)
            ? "Automatic shutdown is paused until the device has been idle for 60 continuous seconds."
            : "No known work apps or visible application windows were found; the inactivity safety check is active.";
        if (idleDuration < TimeSpan.FromSeconds(60))
        {
            _secondsRemaining = 60;
            RecordBlocked("User activity resumed during the shutdown countdown.");
            UpdateCountdownLabel();
            return;
        }

        if (_auditFailed)
        {
            _secondsRemaining = 60;
            UpdateCountdownLabel();
            return;
        }

        _secondsRemaining--;
        UpdateCountdownLabel();
        if (_secondsRemaining > 0)
        {
            return;
        }

        _timer.Stop();
        try
        {
            if (_requestShutdown())
            {
                _allowClose = true;
                Close();
                return;
            }

            _safetyLabel.Text = "HIOP could not safely record the shutdown request. The computer will stay on.";
        }
        catch (IOException)
        {
            _safetyLabel.Text = "HIOP could not safely record the shutdown request. The computer will stay on.";
        }
        catch (UnauthorizedAccessException)
        {
            _safetyLabel.Text = "HIOP could not safely record the shutdown request. The computer will stay on.";
        }
        catch (InvalidOperationException)
        {
            _safetyLabel.Text = "Windows did not accept the normal shutdown request. The computer will stay on.";
        }

        _secondsRemaining = 60;
        UpdateCountdownLabel();
        _timer.Start();
    }

    private void OnStayOn(object? sender, EventArgs eventArgs)
    {
        try
        {
            _stayOn(_reasonInput.Text.Trim());
            _timer.Stop();
            _allowClose = true;
            Close();
        }
        catch (IOException)
        {
            _safetyLabel.Text = "HIOP could not save the audit event. Please retry; the computer will remain on.";
        }
        catch (UnauthorizedAccessException)
        {
            _safetyLabel.Text = "HIOP could not save the audit event. Please retry; the computer will remain on.";
        }
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs eventArgs)
    {
        if (!_allowClose && eventArgs.CloseReason == CloseReason.UserClosing)
        {
            eventArgs.Cancel = true;
            _safetyLabel.Text = "To dismiss this reminder, enter a reason and choose Keep computer on.";
        }
    }

    private void RecordBlocked(string reason)
    {
        if (_blockRecorded || _auditFailed)
        {
            return;
        }

        try
        {
            _logBlocked(reason);
            _blockRecorded = true;
        }
        catch (IOException)
        {
            _auditFailed = true;
            _safetyLabel.Text = "Automatic shutdown is paused because HIOP could not save the local audit event.";
        }
        catch (UnauthorizedAccessException)
        {
            _auditFailed = true;
            _safetyLabel.Text = "Automatic shutdown is paused because HIOP could not save the local audit event.";
        }
    }

    private void UpdateCountdownLabel() =>
        _countdownLabel.Text = $"Automatic shutdown in {_secondsRemaining.ToString(CultureInfo.InvariantCulture)} seconds";

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _timer.Stop();
            _timer.Dispose();
        }

        base.Dispose(disposing);
    }
}
