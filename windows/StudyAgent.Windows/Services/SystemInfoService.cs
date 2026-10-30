using System.Runtime.InteropServices;

namespace StudyAgent_Windows.Services;

/// <summary>Local machine facts for diagnostics; nothing here leaves the computer.</summary>
public static class SystemInfoService
{
    /// <summary>Space the recommended Ollama model needs, with headroom (qwen3.5:4b is about 3.3-4 GB).</summary>
    public const long RecommendedModelBytes = 5L * 1024 * 1024 * 1024;

    public static long? FreeDiskBytes()
    {
        try
        {
            string root = Path.GetPathRoot(Path.GetFullPath(AppStorage.DataFolder)) ?? "";
            return string.IsNullOrEmpty(root) ? null : new DriveInfo(root).AvailableFreeSpace;
        }
        catch
        {
            return null;
        }
    }

    public static string Summary()
    {
        long memory = GC.GetGCMemoryInfo().TotalAvailableMemoryBytes;
        string disk = FreeDiskBytes() is long free
            ? FormatBytes(free)
            : LocalizationService.Text("неизвестно", "unknown");
        return $"Windows: {RuntimeInformation.OSDescription} ({RuntimeInformation.OSArchitecture})\n" +
            $"{LocalizationService.Text("Память", "Memory")}: {FormatBytes(memory)}\n" +
            $"{LocalizationService.Text("Свободно на диске", "Free disk space")}: {disk}";
    }

    public static string FormatBytes(long bytes) =>
        bytes >= 1L << 30 ? $"{bytes / (double)(1L << 30):F1} GB" : $"{bytes / (double)(1L << 20):F0} MB";
}
