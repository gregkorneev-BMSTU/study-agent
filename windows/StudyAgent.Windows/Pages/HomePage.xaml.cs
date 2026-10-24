using System;
using System.Linq;
using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using StudyAgent_Windows.Services;
using Windows.System;

namespace StudyAgent_Windows.Pages;

public sealed partial class HomePage : Page
{
    private readonly PythonBridgeService _bridge = new();
    private readonly LibraryStorageService _storage = new();

    public HomePage()
    {
        InitializeComponent();
    }

    private async void SearchButton_Click(
        object sender, RoutedEventArgs e)
    {
        await PerformSearchAsync();
    }

    private async void QueryInput_KeyDown(
        object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == VirtualKey.Enter)
        {
            e.Handled = true;
            await PerformSearchAsync();
        }
    }

    private async System.Threading.Tasks.Task PerformSearchAsync()
    {
        if (!SearchButton.IsEnabled)
            return;

        string query = QueryInput.Text.Trim();

        if (string.IsNullOrWhiteSpace(query))
        {
            SearchStatus.Text = "Введите поисковый запрос.";
            return;
        }

        SearchButton.IsEnabled = false;
        QueryInput.IsEnabled = false;
        SearchProgress.IsActive = true;
        SearchStatus.Text = "Ищем документы...";
        ResultsPanel.Children.Clear();

        try
        {
            string[] roots = _storage.Load()
                .Where(path => !string.IsNullOrWhiteSpace(path))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

            if (roots.Length == 0)
            {
                SearchStatus.Text =
                    "Сначала добавьте папку в разделе «Библиотека».";
                return;
            }

            using var response =
                await _bridge.SearchAsync(roots, query);

            JsonElement hits = response.RootElement
                .GetProperty("result")
                .GetProperty("hits");

            int count = hits.GetArrayLength();

            if (count == 0)
            {
                SearchStatus.Text =
                    "Ничего не найдено. Попробуйте другой запрос.";
                return;
            }

            SearchStatus.Text = $"Найдено результатов: {count}";

            foreach (JsonElement hit in hits.EnumerateArray())
            {
                string title = hit.GetProperty("title")
                    .GetString() ?? "Без названия";

                string excerpt = hit.GetProperty("excerpt")
                    .GetString() ?? "";

                string documentId = hit.GetProperty("document_id")
                    .GetString() ?? "";

                string sourceRoot = hit.GetProperty("source_root")
                    .GetString() ?? "";

                double score = hit.GetProperty("score")
                    .GetDouble();

                AddResult(
                    title, excerpt, sourceRoot,
                    documentId, score);
            }
        }
        catch (Exception ex)
        {
            if (ex.Message.Contains("OCR is unavailable",
        StringComparison.OrdinalIgnoreCase) ||
    ex.Message.Contains("Chandra",
        StringComparison.OrdinalIgnoreCase))
{
    SearchStatus.Text =
        "Некоторые документы требуют распознавания текста (OCR). " +
        "Компонент OCR пока не установлен. " +
        "Попробуйте поиск по папке с текстовыми документами.";
}
else
{
    SearchStatus.Text = $"Ошибка поиска: {ex.Message}";
}
        }
        finally
        {
            SearchButton.IsEnabled = true;
            QueryInput.IsEnabled = true;
            SearchProgress.IsActive = false;
        }
    }

    private void AddResult(
        string title,
        string excerpt,
        string sourceRoot,
        string documentId,
        double score)
    {
        var card = new StackPanel
        {
            Spacing = 8,
            Padding = new Thickness(16)
        };

        card.Children.Add(new TextBlock
        {
            Text = title,
            FontSize = 18,
            FontWeight = new Windows.UI.Text.FontWeight
            {
                Weight = 600
            },
            TextWrapping = TextWrapping.Wrap
        });

        card.Children.Add(new TextBlock
        {
            Text = excerpt,
            TextWrapping = TextWrapping.Wrap,
            MaxLines = 6
        });

        card.Children.Add(new TextBlock
        {
            Text = $"Источник: {sourceRoot}",
            Opacity = 0.7,
            TextWrapping = TextWrapping.Wrap,
            FontSize = 12
        });

        card.Children.Add(new TextBlock
        {
            Text = $"Документ: {documentId} | Оценка: {score:F2}",
            Opacity = 0.7,
            TextWrapping = TextWrapping.Wrap,
            FontSize = 12
        });

        ResultsPanel.Children.Add(new Border
        {
            Child = card,
            BorderThickness = new Thickness(1),
            BorderBrush = (Microsoft.UI.Xaml.Media.Brush)
                Application.Current.Resources[
                    "CardStrokeColorDefaultBrush"],
            CornerRadius = new CornerRadius(8)
        });
    }
}

