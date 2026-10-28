using System.Globalization;
using Windows.Storage;

namespace StudyAgent_Windows.Services;

public static class LocalizationService
{
    public static string CurrentLanguage
    {
        get
        {
            object? selected = ApplicationData.Current.LocalSettings.Values["AppLanguage"];
            if (selected is string language && (language == "ru" || language == "en"))
                return language;
            return CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "ru" ? "ru" : "en";
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
