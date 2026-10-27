namespace Hiop.Agent.Tray;

internal sealed class EnrollmentDialog : Form
{
    private readonly TextBox _tokenInput;

    public string EnrollmentToken => _tokenInput.Text.Trim();

    public EnrollmentDialog()
    {
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
            Text = "Paste the one-time connection code generated from HIOP Local Agents.",
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
