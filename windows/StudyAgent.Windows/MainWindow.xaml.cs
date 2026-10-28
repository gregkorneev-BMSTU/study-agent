
using System;
using System.Threading.Tasks;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using StudyAgent_Windows.Pages;

namespace StudyAgent_Windows;

public sealed partial class MainWindow : Window
{
    public static MainWindow? ActiveWindow { get; private set; }
    public MainWindow()
    {
        InitializeComponent();
        ActiveWindow = this;
        Closed += (_, _) => Services.PythonBridgeService.TerminateAll();
        ApplyLanguage();

        string savedTheme = Services.AppStorage.GetSetting("AppTheme") as string ?? "System";

        if (Content is FrameworkElement root)
        {
            root.RequestedTheme = savedTheme switch
            {
                "Light" => ElementTheme.Light,
                "Dark" => ElementTheme.Dark,
                _ => ElementTheme.Default
            };
        }

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);
        AppWindow.TitleBar.PreferredHeightOption = TitleBarHeightOption.Tall;
        AppWindow.SetIcon("Assets/AppIcon.ico");
        if (Content is FrameworkElement contentRoot)
            contentRoot.Loaded += (_, _) => contentRoot.DispatcherQueue.TryEnqueue(() =>
            {
                if (Services.AppStorage.GetSetting("WelcomeShown") is null)
                    _ = ShowWelcomeAsync();
            });
    }

    public async Task ShowWelcomeAsync()
    {
        string language = Services.LocalizationService.CurrentLanguage;
        var dialog = new ContentDialog
        {
            Title = language == "ru" ? "Добро пожаловать в Study Agent" : "Welcome to Study Agent",
            Content = language == "ru"
                ? "Study Agent индексирует выбранные вами локальные папки. Поиск работает на этом компьютере; ответы генерирует выбранная локальная модель Ollama. Добавьте папку, чтобы начать."
                : "Study Agent indexes local folders you choose. Search stays on this computer; answers use a local Ollama model. Add a folder to get started.",
            PrimaryButtonText = language == "ru" ? "Настроить библиотеку" : "Set up library",
            CloseButtonText = language == "ru" ? "Позже" : "Later",
            XamlRoot = Content.XamlRoot
        };
        bool goToLibrary = await dialog.ShowAsync() == ContentDialogResult.Primary;
        Services.AppStorage.SetSetting("WelcomeShown", true);
        if (goToLibrary)
        {
            NavView.SelectedItem = LibraryNavItem;
            NavFrame.Navigate(typeof(LibraryPage));
        }
    }

    public void ApplyLanguage()
    {
        SearchNavItem.Content =
            Services.LocalizationService.Text("Поиск", "Search");

        LibraryNavItem.Content =
            Services.LocalizationService.Text("Библиотека", "Library");

        AboutNavItem.Content =
            Services.LocalizationService.Text("О программе", "About");

        SettingsNavItem.Content =
            Services.LocalizationService.Text("Настройки", "Settings");
    }
    private void TitleBar_PaneToggleRequested(
        TitleBar sender, object args)
    {
        NavView.IsPaneOpen = !NavView.IsPaneOpen;
    }

    private void TitleBar_BackRequested(
        TitleBar sender, object args)
    {
        if (NavFrame.CanGoBack)
        {
            NavFrame.GoBack();
        }
    }

    private void NavView_SelectionChanged(
        NavigationView sender,
        NavigationViewSelectionChangedEventArgs args)
    {
        if (args.IsSettingsSelected)
        {
            NavFrame.Navigate(typeof(SettingsPage));
            return;
        }

        if (args.SelectedItem is not NavigationViewItem item)
        {
            return;
        }

        switch (item.Tag?.ToString())
        {
            case "search":
                NavFrame.Navigate(typeof(HomePage));
                break;

            case "library":
                NavFrame.Navigate(typeof(LibraryPage));
                break;

            case "settings":
                NavFrame.Navigate(typeof(SettingsPage));
                break;

            case "about":
                NavFrame.Navigate(typeof(AboutPage));
                break;
        }
    }
}


