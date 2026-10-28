using System;
using Microsoft.UI.Xaml.Controls;
using StudyAgent_Windows.Services;
using Windows.ApplicationModel;

namespace StudyAgent_Windows.Pages;

public sealed partial class AboutPage : Page
{
    public AboutPage()
    {
        InitializeComponent();
        ApplyLanguage();
        LoadVersion();
    }

    private static string T(string ru, string en)
    {
        return LocalizationService.Text(ru, en);
    }

    private void ApplyLanguage()
    {
        AboutTitle.Text =
            T("О программе", "About");

        AboutSubtitle.Text =
            T(
                "Study Agent — локальный помощник для работы с учебными материалами.",
                "Study Agent is a local assistant for working with study materials.");

        VersionLabel.Text =
            T("Версия приложения", "Application Version");

        DescriptionText.Text =
            T(
                "Приложение позволяет подключать учебные папки, искать документы и генерировать ответы с помощью локальных языковых моделей через Ollama.",
                "Connect study folders, search documents, and generate answers using local language models through Ollama.");

        PrivacyText.Text =
            T(
                "Учебные материалы обрабатываются локально. Для генерации ответов используется локальный сервер Ollama.",
                "Study materials are processed locally. Answer generation uses a local Ollama server.");
    }

    private void LoadVersion()
    {
        try
        {
            var version = Package.Current.Id.Version;

            VersionValue.Text =
                $"{version.Major}.{version.Minor}.{version.Build}.{version.Revision}";
        }
        catch (Exception)
        {
            VersionValue.Text = typeof(App).Assembly.GetName().Version?.ToString()
                ?? T("Недоступна", "Unavailable");
        }
    }
}
