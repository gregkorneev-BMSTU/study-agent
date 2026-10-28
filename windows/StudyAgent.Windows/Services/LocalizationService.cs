using System.Globalization;

namespace StudyAgent_Windows.Services;

public static class LocalizationService
{
    public static string CurrentLanguage
    {
        get
        {
            object? selected = AppStorage.GetSetting("AppLanguage");
            if (selected is string language && (language == "ru" || language == "en"))
                return language;
            return CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "ru" ? "ru" : "en";
        }
        set
        {
            AppStorage.SetSetting("AppLanguage", value);
        }
    }

    public static string Text(string russian, string english)
    {
        return CurrentLanguage == "en" ? english : russian;
    }
}
