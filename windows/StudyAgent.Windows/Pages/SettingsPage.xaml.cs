using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System;
using System.Threading;
using Windows.System;
using StudyAgent_Windows.Services;

namespace StudyAgent_Windows.Pages;

public sealed partial class SettingsPage : Page
{
    private bool _initialized;
    private CancellationTokenSource? _modelDownload;
    private readonly OllamaSetupService _ollamaSetup = new();

    public SettingsPage()
    {
        InitializeComponent();

        string theme = AppStorage.GetSetting("AppTheme") as string ?? "System";

        ThemeCombo.SelectedIndex = theme switch
        {
            "Light" => 1,
            "Dark" => 2,
            _ => 0
        };

        LanguageCombo.SelectedIndex =
            LocalizationService.CurrentLanguage == "en" ? 1 : 0;

        SimilaritySlider.Value = SearchPreferences.MinimumSimilarity;
        DocumentPrefixInput.Text = SearchPreferences.DocumentPrefix;
        QueryPrefixInput.Text = SearchPreferences.QueryPrefix;

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

        SearchSettingsHeading.Text = T("Поиск по материалам", "Search settings");
        SimilarityLabel.Text = T("Порог сходства", "Similarity threshold");
        SimilarityValue.Text = SimilaritySlider.Value.ToString("F2");
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(
            SimilaritySlider, T("Порог сходства", "Similarity threshold"));
        SimilarityDescription.Text = T(
            "Совпадения по смыслу ниже этого порога исключаются из результатов.",
            "Semantic matches below this threshold are excluded from the results.");
        EmbeddingPrefixesExpander.Header = T("Префиксы embedding-модели", "Embedding model prefixes");
        DocumentPrefixInput.Header = T("Префикс документов", "Document prefix");
        QueryPrefixInput.Header = T("Префикс запросов", "Query prefix");
        PrefixDescription.Text = T(
            "Оставьте пустыми, если модель не требует префиксов. Используйте значения из документации выбранной модели.",
            "Leave these empty if your model does not require prefixes. Use the values from its documentation.");
        ProfileChangedDescription.Text = T(
            "После изменения префиксов подготовьте семантический индекс заново на странице поиска.",
            "After changing prefixes, prepare the semantic index again on the Search page.");

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
        InstallModelButton.Content = T("Установить рекомендованную модель qwen3.5:4b", "Install recommended model qwen3.5:4b");
        OpenOllamaButton.Content = T("Установить Ollama", "Install Ollama");
        CancelModelButton.Content = T("Отменить", "Cancel");

        PrivacyHeading.Text =
            T("Конфиденциальность", "Privacy");

        PrivacySubheading.Text =
            T("Локальная обработка", "Local Processing");

        PrivacyDescription.Text =
            T("Study Agent обрабатывает выбранные учебные материалы на компьютере. Для генерации ответа вопрос и найденные выдержки передаются локальному серверу Ollama.",
              "Study Agent processes selected study materials on your computer. Your question and relevant excerpts are sent only to the local Ollama server.");

        AccessibilityHeading.Text = T("Доступность Windows", "Windows accessibility");
        AccessibilityDescription.Text = T(
            "Повышенную контрастность и уменьшение движения можно настроить системными средствами Windows.",
            "Use Windows accessibility settings for contrast themes and reduced motion.");
        ContrastButton.Content = T("Повышенная контрастность", "Contrast themes");
        MotionButton.Content = T("Уменьшение движения", "Reduce motion");
        SetupHeading.Text = T("Первоначальная настройка", "Getting started");
        SetupDescription.Text = T(
            "Откройте мастер приветствия; диагностика компонентов доступна в Библиотеке.",
            "Replay the welcome guide; component diagnostics are available in Library.");
        ReplayWelcomeButton.Content = T("Открыть мастер настройки", "Open setup guide");
    }

    private async void ReplayWelcomeButton_Click(object sender, RoutedEventArgs e)
    {
        if (MainWindow.ActiveWindow is MainWindow window)
            await window.ShowWelcomeAsync();
    }

    private async void ContrastButton_Click(object sender, RoutedEventArgs e) =>
        await Launcher.LaunchUriAsync(new Uri("ms-settings:easeofaccess-highcontrast"));

    private async void MotionButton_Click(object sender, RoutedEventArgs e) =>
        await Launcher.LaunchUriAsync(new Uri("ms-settings:easeofaccess-display"));

    private async void InstallModelButton_Click(object sender, RoutedEventArgs e)
    {
        _modelDownload = new CancellationTokenSource();
        InstallModelButton.IsEnabled = false;
        CancelModelButton.IsEnabled = true;
        ModelInstallProgress.Visibility = Visibility.Visible;
        ModelInstallProgress.IsIndeterminate = true;
        ModelInstallStatus.Text = T("Загрузка модели начинается только после вашего нажатия. Она может занять значительное место.",
            "The model download starts only after your click and may use significant disk space.");
        var progress = new Progress<(string Status, long? Completed, long? Total)>(value =>
        {
            ModelInstallStatus.Text = value.Status;
            if (value.Completed is long completed && value.Total is long total && total > 0)
            {
                ModelInstallProgress.IsIndeterminate = false;
                ModelInstallProgress.Value = 100.0 * completed / total;
            }
        });
        try
        {
            await _ollamaSetup.PullRecommendedAsync(progress, _modelDownload.Token);
            ModelInstallStatus.Text = T("Загрузка завершена. Обновите список моделей на странице Поиск.",
                "Download complete. Refresh the model list on Search.");
        }
        catch (OperationCanceledException)
        {
            ModelInstallStatus.Text = T("Загрузка модели отменена.", "Model download cancelled.");
        }
        catch (Exception ex)
        {
            ModelInstallStatus.Text = T("Ollama недоступна или не смогла загрузить модель. Установить Ollama можно с ollama.com/download. ",
                "Ollama is unavailable or could not download the model. Install Ollama from ollama.com/download. ") + ex.Message;
        }
        finally
        {
            _modelDownload.Dispose();
            _modelDownload = null;
            InstallModelButton.IsEnabled = true;
            CancelModelButton.IsEnabled = false;
            ModelInstallProgress.IsIndeterminate = false;
            ModelInstallProgress.Visibility = Visibility.Collapsed;
        }
    }

    private void CancelModelButton_Click(object sender, RoutedEventArgs e) => _modelDownload?.Cancel();

    private void SimilaritySlider_ValueChanged(
        object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (!_initialized) return;
        SearchPreferences.MinimumSimilarity = e.NewValue;
        SimilarityValue.Text = e.NewValue.ToString("F2");
    }

    private void DocumentPrefixInput_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (_initialized) SearchPreferences.DocumentPrefix = DocumentPrefixInput.Text;
    }

    private void QueryPrefixInput_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (_initialized) SearchPreferences.QueryPrefix = QueryPrefixInput.Text;
    }

    private async void OpenOllamaButton_Click(object sender, RoutedEventArgs e) =>
        await Launcher.LaunchUriAsync(new Uri("https://ollama.com/download"));

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

        AppStorage.SetSetting("AppTheme", theme);

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
