using Hiop.Agent.Tray;

ApplicationConfiguration.Initialize();
try
{
    Application.Run(new AgentTrayContext());
}
catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
{
    MessageBox.Show(
        $"HIOP Agent could not load its local power event queue: {exception.Message}",
        "HIOP Agent",
        MessageBoxButtons.OK,
        MessageBoxIcon.Error);
    Environment.ExitCode = 1;
}
