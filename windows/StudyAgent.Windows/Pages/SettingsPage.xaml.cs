using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage;
using StudyAgent_Windows.Services;

namespace StudyAgent_Windows.Pages;

public sealed partial class SettingsPage : Page
{
    private bool _initialized;

    public SettingsPage()
    {
        InitializeComponent();

        string theme = ApplicationData.Current.LocalSettings
            .Values["AppTheme"] as string ?? "System";

        ThemeCombo.SelectedIndex = theme switch
        {
            "Light" => 1,
            "Dark" => 2,
            _ => 0
        };

        LanguageCombo.SelectedIndex =
            LocalizationService.CurrentLanguage == "en" ? 1 : 0;

        ApplyLanguage();
        _initialized = true;
    }

    private static string T(string russian, string english)
    {
        return LocalizationService.Text(russian, english);
    }

    private void ApplyLanguage()
    {
        SettingsTitle.Text =
            T("Настройки", "Settings");

        SettingsSubtitle.Text =
            T("Настройте Study Agent под свои предпочтения.",
              "Customize Study Agent to your preferences.");

        LanguageHeading.Text =
            T("Язык интерфейса", "Interface Language");

        LanguageCombo.Header =
            T("Язык", "Language");

        AppearanceHeading.Text =
            T("Внешний вид и доступность",
              "Appearance and Accessibility");

        ThemeHeading.Text =
            T("Цветовая тема", "Color Theme");

        ThemeDescription.Text =
            T("Выберите оформление приложения.",
              "Choose the application's appearance.");

        SystemThemeItem.Content =
            T("Системная", "System");

        LightThemeItem.Content =
            T("Светлая", "Light");

        DarkThemeItem.Content =
            T("Тёмная", "Dark");

        // Refresh the selected item's displayed text after localization.
        int selectedTheme = ThemeCombo.SelectedIndex;

        if (selectedTheme >= 0)
        {
            bool wasInitialized = _initialized;
            _initialized = false;

            ThemeCombo.SelectedIndex = -1;
            ThemeCombo.SelectedIndex = selectedTheme;

            _initialized = wasInitialized;
        }

        ModelHeading.Text =
            T("Локальная языковая модель",
              "Local Language Model");

        ModelDescription.Text =
            T("Для генерации ответов используется локальная Ollama. Выбрать установленную модель пока можно на странице поиска.",
              "Answers are generated using local Ollama. For now, you can select an installed model on the Search page.");

        PrivacyHeading.Text =
            T("Конфиденциальность", "Privacy");

        PrivacySubheading.Text =
            T("Локальная обработка", "Local Processing");

        PrivacyDescription.Text =
            T("Study Agent обрабатывает выбранные учебные материалы на компьютере. Для генерации ответа вопрос и найденные выдержки передаются локальному серверу Ollama.",
              "Study Agent processes selected study materials on your computer. Your question and relevant excerpts are sent only to the local Ollama server.");
    }

    private void LanguageCombo_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (!_initialized)
            return;

        LocalizationService.CurrentLanguage =
            LanguageCombo.SelectedIndex == 1 ? "en" : "ru";

        MainWindow.ActiveWindow?.ApplyLanguage();
        ApplyLanguage();
    }

    private void ThemeCombo_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (!_initialized)
            return;

        string theme = ThemeCombo.SelectedIndex switch
        {
            1 => "Light",
            2 => "Dark",
            _ => "System"
        };

        ApplicationData.Current.LocalSettings
            .Values["AppTheme"] = theme;

        ApplyTheme(theme);
    }

    private static void ApplyTheme(string theme)
    {
        if (MainWindow.ActiveWindow?.Content is not FrameworkElement root)
            return;

        root.RequestedTheme = theme switch
        {
            "Light" => ElementTheme.Light,
            "Dark" => ElementTheme.Dark,
            _ => ElementTheme.Default
        };
    }
}
