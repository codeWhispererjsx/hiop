namespace Hiop.Agent.Tray;

internal sealed class EnrollmentDialog : Form
{
    private readonly TextBox _tokenInput;

    public string EnrollmentToken => _tokenInput.Text.Trim();

    public EnrollmentDialog()
    {
        // Layout below is in 96-DPI pixels; scale it with the display so text is not clipped at 125%+.
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        Text = "Connect this computer to HIOP";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterScreen;
        MinimizeBox = false;
        MaximizeBox = false;
        ShowInTaskbar = true;
        Width = 560;
        Height = 220;

        var lead = new Label
        {
            Text = "In HIOP, open Agents and choose Connect a computer. Paste the one-time code here.",
            AutoSize = true,
            Left = 18,
            Top = 18,
        };
        _tokenInput = new TextBox
        {
            Left = 18,
            Top = 54,
            Width = 505,
            Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
        };
        var connect = new Button
        {
            Text = "Connect",
            DialogResult = DialogResult.OK,
            Left = 343,
            Top = 103,
            Width = 85,
        };
        var cancel = new Button
        {
            Text = "Cancel",
            DialogResult = DialogResult.Cancel,
            Left = 438,
            Top = 103,
            Width = 85,
        };

        connect.Click += (_, _) =>
        {
            if (string.IsNullOrWhiteSpace(_tokenInput.Text))
            {
                MessageBox.Show("Paste the one-time connection code first.", "HIOP Agent", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                DialogResult = DialogResult.None;
            }
        };

        Controls.AddRange([lead, _tokenInput, connect, cancel]);
        AcceptButton = connect;
        CancelButton = cancel;
    }
}
