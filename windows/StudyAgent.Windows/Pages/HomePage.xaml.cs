using System;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
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

    private JsonElement[] _lastHits = Array.Empty<JsonElement>();
    private string _lastQuery = "";
    private bool _busy;

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

    private async Task PerformSearchAsync()
    {
        if (_busy)
            return;

        string query = QueryInput.Text.Trim();

        if (string.IsNullOrWhiteSpace(query))
        {
            SearchStatus.Text = "Введите поисковый запрос.";
            return;
        }

        SetBusy(true);
        _lastHits = Array.Empty<JsonElement>();
        _lastQuery = "";
        ResultsPanel.Children.Clear();
        AnswerText.Text = "Ожидание результатов поиска...";
        SearchStatus.Text = "Ищем документы...";

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
                AnswerText.Text = "Нет подключённых документов.";
                return;
            }

            using var response =
                await _bridge.SearchAsync(roots, query);

            JsonElement hits = response.RootElement
                .GetProperty("result")
                .GetProperty("hits");

            _lastHits = hits.EnumerateArray()
                .Select(hit => hit.Clone())
                .ToArray();

            _lastQuery = query;

            if (_lastHits.Length == 0)
            {
                SearchStatus.Text = "Ничего не найдено.";
                AnswerText.Text =
                    "Для генерации ответа нужны найденные материалы.";
                return;
            }

            SearchStatus.Text =
                $"Найдено результатов: {_lastHits.Length}";

            foreach (JsonElement hit in _lastHits)
            {
                string title = hit.GetProperty("title")
                    .GetString() ?? "Без названия";

                string excerpt = hit.GetProperty("excerpt")
                    .GetString() ?? "";

                string documentId = hit.GetProperty("document_id")
                    .GetString() ?? "";

                string sourceRoot = hit.GetProperty("source_root")
                    .GetString() ?? "";

                double score = hit.GetProperty("score").GetDouble();

                AddResult(title, excerpt, sourceRoot, documentId, score);
            }

            AnswerText.Text =
                "Документы найдены. Выберите модель Ollama " +
                "и нажмите «Сгенерировать ответ».";
        }
        catch (Exception ex)
        {
            if (ex.Message.Contains("OCR is unavailable",
                    StringComparison.OrdinalIgnoreCase) ||
                ex.Message.Contains("Chandra",
                    StringComparison.OrdinalIgnoreCase))
            {
                SearchStatus.Text =
                    "Некоторым документам требуется OCR, " +
                    "который пока не установлен.";
            }
            else
            {
                SearchStatus.Text =
                    $"Ошибка поиска: {ex.Message}";
            }

            AnswerText.Text =
                "Генерация недоступна, поскольку поиск не завершился.";
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void RefreshModelsButton_Click(
        object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;

        SetBusy(true);
        ModelsComboBox.Items.Clear();
        OllamaStatus.Text = "Проверяем Ollama...";

        try
        {
            using var response = await _bridge.ListModelsAsync();

            JsonElement models = response.RootElement
                .GetProperty("result")
                .GetProperty("models");

            foreach (JsonElement model in models.EnumerateArray())
            {
                string? name = model.GetString();

                if (!string.IsNullOrWhiteSpace(name))
                    ModelsComboBox.Items.Add(name);
            }

            if (ModelsComboBox.Items.Count == 0)
            {
                OllamaStatus.Text =
                    "Ollama доступна, но модели не установлены.";
            }
            else
            {
                ModelsComboBox.SelectedIndex = 0;
                OllamaStatus.Text =
                    $"Доступно моделей: {ModelsComboBox.Items.Count}";
            }
        }
        catch (Exception ex)
        {
            OllamaStatus.Text =
                "Ollama не найдена или не запущена. " +
                "Её можно установить позже. " +
                $"Подробности: {ex.Message}";
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void GenerateButton_Click(
        object sender, RoutedEventArgs e)
    {
        if (_busy || _lastHits.Length == 0 ||
            ModelsComboBox.SelectedItem is not string model)
        {
            return;
        }

        SetBusy(true);
        AnswerText.Text =
            "Генерируем ответ. Локальная модель может работать долго...";

        try
        {
            using var response = await _bridge.AnswerAsync(
                model,
                _lastQuery,
                _lastHits.Take(5).ToArray());

            AnswerText.Text = response.RootElement
                .GetProperty("result")
                .GetProperty("answer")
                .GetString() ?? "Модель вернула пустой ответ.";
        }
        catch (Exception ex)
        {
            AnswerText.Text =
                $"Не удалось получить ответ: {ex.Message}";
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;

        SearchButton.IsEnabled = !busy;
        QueryInput.IsEnabled = !busy;
        RefreshModelsButton.IsEnabled = !busy;
        ModelsComboBox.IsEnabled = !busy;
        GenerateButton.IsEnabled = !busy &&
            _lastHits.Length > 0 &&
            ModelsComboBox.SelectedItem is string;

        SearchProgress.IsActive = busy;
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
