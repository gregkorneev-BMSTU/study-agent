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
        ApplyLanguage();
    }

    private static string T(string ru, string en)
    {
        return LocalizationService.Text(ru, en);
    }


    private void ApplyLanguage()
    {
        SearchTitle.Text =
            T("Поиск по учебным материалам", "Search Study Materials");

        SearchSubtitle.Text =
            T("Поиск документов и ответы на вопросы",
              "Search documents and get answers to questions");

        QueryInput.PlaceholderText =
            T("Введите вопрос или поисковый запрос...",
              "Enter a question or search query...");

        SearchButton.Content = T("Найти", "Search");

        ModelHeading.Text =
            T("Локальная языковая модель", "Local Language Model");

        ModelsComboBox.PlaceholderText =
            T("Модель не выбрана", "No model selected");

        RefreshModelsButton.Content =
            T("Обновить модели", "Refresh Models");

        GenerateButton.Content =
            T("Сгенерировать ответ", "Generate Answer");

        OllamaStatus.Text =
            T("Нажмите «Обновить модели», чтобы проверить Ollama.",
              "Click Refresh Models to check Ollama.");

        SearchStatus.Text =
            T("Введите запрос для поиска.", "Enter a search query.");

        AnswerHeading.Text =
            T("Ответ по найденным материалам",
              "Answer Based on Found Materials");

        AnswerText.Text =
            T("После поиска выберите модель и нажмите «Сгенерировать ответ».",
              "After searching, select a model and click Generate Answer.");
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
            SearchStatus.Text = T("Введите поисковый запрос.", "Enter a search query.");
            return;
        }

        SetBusy(true);
        _lastHits = Array.Empty<JsonElement>();
        _lastQuery = "";
        ResultsPanel.Children.Clear();
        AnswerText.Text = T("Ожидание результатов поиска...", "Waiting for search results...");
        SearchStatus.Text = T("Ищем документы...", "Searching documents...");

        try
        {
            string[] roots = _storage.Load()
                .Where(path => !string.IsNullOrWhiteSpace(path))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

            if (roots.Length == 0)
            {
                SearchStatus.Text =
                    T("Сначала добавьте папку в разделе «Библиотека».", "First add a folder in Library.");
                AnswerText.Text = T("Нет подключённых документов.", "No documents are connected.");
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
                SearchStatus.Text = T("Ничего не найдено.", "No results found.");
                AnswerText.Text =
                    T("Для генерации ответа нужны найденные материалы.", "Matching documents are required to generate an answer.");
                return;
            }

            SearchStatus.Text =
                $"{T("Найдено результатов", "Results found")}: {_lastHits.Length}";

            foreach (JsonElement hit in _lastHits)
            {
                string title = hit.GetProperty("title")
                    .GetString() ?? T("Без названия", "Untitled");

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
                T("Документы найдены. Выберите модель Ollama ", "Documents found. Select an Ollama model ") +
                T("и нажмите «Сгенерировать ответ».", "and click Generate Answer.");
        }
        catch (Exception ex)
        {
            if (ex.Message.Contains("OCR is unavailable",
                    StringComparison.OrdinalIgnoreCase) ||
                ex.Message.Contains("Chandra",
                    StringComparison.OrdinalIgnoreCase))
            {
                SearchStatus.Text =
                    T("Некоторым документам требуется OCR, ", "Some documents require OCR, ") +
                    T("который пока не установлен.", "which is not installed yet.");
            }
            else
            {
                SearchStatus.Text =
                    $"{T("Ошибка поиска", "Search error")}: {ex.Message}";
            }

            AnswerText.Text =
                T("Генерация недоступна, поскольку поиск не завершился.", "Answer generation is unavailable because the search did not finish.");
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
        OllamaStatus.Text = T("Проверяем Ollama...", "Checking Ollama...");

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
                    T("Ollama доступна, но модели не установлены.", "Ollama is available, but no models are installed.");
            }
            else
            {
                ModelsComboBox.SelectedIndex = 0;
                OllamaStatus.Text =
                    $"{T("Доступно моделей", "Available models")}: {ModelsComboBox.Items.Count}";
            }
        }
        catch (Exception ex)
        {
            OllamaStatus.Text =
                T("Ollama не найдена или не запущена. ", "Ollama was not found or is not running. ") +
                T("Её можно установить позже. ", "You can install it later. ") +
                $"{T("Подробности", "Details")}: {ex.Message}";
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
            T("Генерируем ответ. Локальная модель может работать долго...", "Generating an answer. The local model may take some time...");

        try
        {
            using var response = await _bridge.AnswerAsync(
                model,
                _lastQuery,
                _lastHits.Take(5).ToArray());

            AnswerText.Text = response.RootElement
                .GetProperty("result")
                .GetProperty("answer")
                .GetString() ?? T("Модель вернула пустой ответ.", "The model returned an empty answer.");
        }
        catch (Exception ex)
        {
            AnswerText.Text =
                $"{T("Не удалось получить ответ", "Could not generate an answer")}: {ex.Message}";
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
            Text = $"{T("Источник", "Source")}: {sourceRoot}",
            Opacity = 0.7,
            TextWrapping = TextWrapping.Wrap,
            FontSize = 12
        });

        card.Children.Add(new TextBlock
        {
            Text = $"{T("Документ", "Document")}: {documentId} | {T("Оценка", "Score")}: {score:F2}",
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
