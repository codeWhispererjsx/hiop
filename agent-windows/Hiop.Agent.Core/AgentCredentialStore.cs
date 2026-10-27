using System.Security.Cryptography;
using System.Text;

namespace Hiop.Agent.Core;

public sealed class AgentCredentialStore(string dataDirectory)
{
    private static readonly byte[] Entropy = Encoding.UTF8.GetBytes("HIOP.Agent.Credential.v1");
    private readonly string _credentialPath = Path.Combine(dataDirectory, "credential.dpapi");

    public bool Exists => File.Exists(_credentialPath);

    public string? Load()
    {
        if (!File.Exists(_credentialPath))
        {
            return null;
        }

        var encrypted = File.ReadAllBytes(_credentialPath);
        var clear = ProtectedData.Unprotect(encrypted, Entropy, DataProtectionScope.LocalMachine);
        return Encoding.UTF8.GetString(clear);
    }

    public void Save(string credential)
    {
        if (string.IsNullOrWhiteSpace(credential))
        {
            throw new ArgumentException("An agent credential is required.", nameof(credential));
        }

        Directory.CreateDirectory(Path.GetDirectoryName(_credentialPath)!);
        var clear = Encoding.UTF8.GetBytes(credential);
        var encrypted = ProtectedData.Protect(clear, Entropy, DataProtectionScope.LocalMachine);
        var temporaryPath = _credentialPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                stream.Write(encrypted);
                stream.Flush(true);
            }

            File.Move(temporaryPath, _credentialPath, true);
        }
        finally
        {
            if (File.Exists(temporaryPath))
            {
                File.Delete(temporaryPath);
            }
        }
    }

    public void Delete()
    {
        if (File.Exists(_credentialPath))
        {
            File.Delete(_credentialPath);
        }
    }
}
