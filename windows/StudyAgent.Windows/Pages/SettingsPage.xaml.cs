using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage;

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

        _initialized = true;
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
