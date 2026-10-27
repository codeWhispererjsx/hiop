using System.Management;
using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace Hiop.Agent.Service;

public static class LocalWindowsInventory
{
    public static Dictionary<string, object?> Collect()
    {
        var system = ReadSingle("Win32_ComputerSystem", "Manufacturer", "Model", "TotalPhysicalMemory");
        var bios = ReadSingle("Win32_BIOS", "SerialNumber");
        var operatingSystem = ReadSingle("Win32_OperatingSystem", "Caption", "Version", "OSArchitecture");
        var processor = ReadSingle("Win32_Processor", "Name", "NumberOfCores");
        var adapters = NetworkInterface.GetAllNetworkInterfaces()
            .Where(adapter =>
                adapter.OperationalStatus == OperationalStatus.Up &&
                adapter.NetworkInterfaceType is not NetworkInterfaceType.Loopback and not NetworkInterfaceType.Tunnel)
            .SelectMany(adapter =>
            {
                var mac = NormalizeMac(adapter.GetPhysicalAddress().ToString());
                if (mac is null)
                {
                    return [];
                }

                return adapter.GetIPProperties().UnicastAddresses
                    .Where(address => address.Address.AddressFamily is AddressFamily.InterNetwork or AddressFamily.InterNetworkV6)
                    .Select(address => new Dictionary<string, object?>
                    {
                        ["ip_address"] = address.Address.ToString(),
                        ["mac_address"] = mac,
                        ["mac_address_source"] = "local_adapter",
                        ["adapter_name"] = adapter.Name,
                        ["adapter_type"] = adapter.NetworkInterfaceType.ToString(),
                    });
            })
            .ToArray();

        return new Dictionary<string, object?>
        {
            ["hostname"] = Environment.MachineName,
            ["serial_number"] = CleanValue(bios.GetValueOrDefault("SerialNumber")?.ToString()),
            ["manufacturer"] = CleanValue(system.GetValueOrDefault("Manufacturer")?.ToString()),
            ["model"] = CleanValue(system.GetValueOrDefault("Model")?.ToString()),
            ["operating_system"] = CleanValue(operatingSystem.GetValueOrDefault("Caption")?.ToString()),
            ["operating_system_version"] = CleanValue(operatingSystem.GetValueOrDefault("Version")?.ToString()),
            ["operating_system_architecture"] = CleanValue(operatingSystem.GetValueOrDefault("OSArchitecture")?.ToString()),
            ["memory_bytes"] = system.GetValueOrDefault("TotalPhysicalMemory"),
            ["processor"] = CleanValue(processor.GetValueOrDefault("Name")?.ToString()),
            ["processor_cores"] = processor.GetValueOrDefault("NumberOfCores"),
            ["memory"] = system.GetValueOrDefault("TotalPhysicalMemory"),
            ["cpu"] = CleanValue(processor.GetValueOrDefault("Name")?.ToString()),
            ["nics"] = adapters,
            ["network_adapters"] = adapters,
        };
    }

    public static string? NormalizeMac(string? value)
    {
        var hex = new string((value ?? string.Empty).Where(Uri.IsHexDigit).ToArray()).ToLowerInvariant();
        if (hex.Length != 12 || hex.All(character => character == '0') || hex.All(character => character == 'f'))
        {
            return null;
        }

        return string.Join(':', Enumerable.Range(0, 6).Select(index => hex.Substring(index * 2, 2)));
    }

    private static Dictionary<string, object?> ReadSingle(string className, params string[] properties)
    {
        var selected = string.Join(", ", properties);
        using var searcher = new ManagementObjectSearcher($"SELECT {selected} FROM {className}");
        using var results = searcher.Get();
        var first = results.Cast<ManagementObject>().FirstOrDefault();
        if (first is null)
        {
            throw new InvalidOperationException($"Windows did not return {className} inventory data.");
        }

        return properties.ToDictionary(
            property => property,
            property => (object?)first[property],
            StringComparer.OrdinalIgnoreCase);
    }

    private static string? CleanValue(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        var cleaned = value.Trim();
        return cleaned.Equals("To be filled by O.E.M.", StringComparison.OrdinalIgnoreCase) ||
               cleaned.Equals("System Product Name", StringComparison.OrdinalIgnoreCase) ||
               cleaned.Equals("Default string", StringComparison.OrdinalIgnoreCase) ||
               cleaned.Equals("N/A", StringComparison.OrdinalIgnoreCase) ||
               cleaned.All(character => character == '0')
            ? null
            : cleaned;
    }
}
