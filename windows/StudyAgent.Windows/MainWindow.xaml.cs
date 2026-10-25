
using System;
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
        ApplyLanguage();

        string savedTheme =
            Windows.Storage.ApplicationData.Current.LocalSettings
                .Values["AppTheme"] as string ?? "System";

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


