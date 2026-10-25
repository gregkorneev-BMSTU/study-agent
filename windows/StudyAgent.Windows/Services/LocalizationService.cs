using Windows.Storage;

namespace StudyAgent_Windows.Services;

public static class LocalizationService
{
    public static string CurrentLanguage
    {
        get
        {
            return ApplicationData.Current.LocalSettings
                .Values["AppLanguage"] as string ?? "ru";
        }
        set
        {
            ApplicationData.Current.LocalSettings
                .Values["AppLanguage"] = value;
        }
    }

    public static string Text(string russian, string english)
    {
        return CurrentLanguage == "en" ? english : russian;
    }
}
