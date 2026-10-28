using System.Runtime.InteropServices;
using System.Text.Json;
using Windows.Storage;

namespace StudyAgent_Windows.Services;

public static class AppStorage
{
    private const int AppModelErrorNoPackage = 15700;
    private static readonly object SettingsLock = new();

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int GetCurrentPackageFullName(ref uint length, char[]? name);

    private static bool HasPackageIdentity()
    {
        uint length = 0;
        return GetCurrentPackageFullName(ref length, null) != AppModelErrorNoPackage;
    }

    private static readonly bool Packaged = HasPackageIdentity();

    public static string LocalFolder => Packaged
        ? ApplicationData.Current.LocalFolder.Path
        : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "StudyAgent");

    public static string DataFolder => Packaged ? Path.Combine(LocalFolder, "StudyAgent") : LocalFolder;

    public static object? GetSetting(string key)
    {
        if (Packaged) return ApplicationData.Current.LocalSettings.Values[key];
        lock (SettingsLock)
        {
            string path = Path.Combine(LocalFolder, "settings.json");
            if (!File.Exists(path)) return null;
            var settings = JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(path))
                ?? new Dictionary<string, string>();
            return settings.GetValueOrDefault(key);
        }
    }

    public static void SetSetting(string key, object? value)
    {
        if (Packaged)
        {
            ApplicationData.Current.LocalSettings.Values[key] = value;
            return;
        }
        lock (SettingsLock)
        {
            Directory.CreateDirectory(LocalFolder);
            string path = Path.Combine(LocalFolder, "settings.json");
            var settings = File.Exists(path)
                ? JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(path))
                    ?? new Dictionary<string, string>()
                : new Dictionary<string, string>();
            if (value is null) settings.Remove(key);
            else settings[key] = value.ToString()!;
            string temporary = path + ".tmp";
            File.WriteAllText(temporary, JsonSerializer.Serialize(settings));
            File.Move(temporary, path, overwrite: true);
        }
    }
}
