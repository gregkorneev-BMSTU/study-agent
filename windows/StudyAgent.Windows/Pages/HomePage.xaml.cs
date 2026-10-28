using System;
using System.Linq;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Input;
using Windows.Storage;
using StudyAgent_Windows.Services;
using Windows.System;

namespace StudyAgent_Windows.Pages;

public sealed partial class HomePage : Page
{
    private readonly PythonBridgeService _bridge = new();
    private readonly LibraryStorageService _storage = new();

    private JsonElement[] _lastHits = Array.Empty<JsonElement>();
    private string _lastQuery = "";
    private string[] _lastRoots = Array.Empty<string>();
    private string _lastMode = "lexical";
    private PythonBridgeService.EmbeddingProfile? _lastEmbedding;
    private bool _busy;
    private bool _loadingOptions;
    private readonly ApplicationDataContainer _settings = ApplicationData.Current.LocalSettings;
    private CancellationTokenSource? _preparation;

    public HomePage()
    {
        InitializeComponent();
        ApplyLanguage();
        AnswerWebView.NavigationCompleted += AnswerWebView_NavigationCompleted;
        AnswerWebView.Source = new System.Uri(Path.Combine(AppContext.BaseDirectory, "assets", "math", "index.html"));
    }

    private async void HomePage_Loaded(object sender, RoutedEventArgs e)
    {
        ApplyLanguage();
        _loadingOptions = true;
        string savedMode = _settings.Values["SearchMode"] as string ?? "lexical";
        SearchModeCombo.SelectedIndex = savedMode switch { "semantic" => 1, "hybrid" => 2, _ => 0 };
        _loadingOptions = false;
        await RefreshEmbeddingModelsAsync();
        await RefreshModelsAsync();
    }

    private async void SearchMode_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (SearchModeCombo.SelectedItem is not ComboBoxItem item) return;
        string mode = item.Tag?.ToString() ?? "lexical";
        _settings.Values["SearchMode"] = mode;
        EmbeddingModelCombo.IsEnabled = mode != "lexical";
        PrepareEmbeddingsButton.IsEnabled = !_busy && SelectedEmbedding() is not null;
        if (!_loadingOptions && mode != "lexical" && EmbeddingModelCombo.Items.Count == 0)
            await RefreshEmbeddingModelsAsync();
    }

    private void EmbeddingModel_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_loadingOptions || EmbeddingModelCombo.SelectedItem is not ComboBoxItem item) return;
        _settings.Values["EmbeddingModel"] = item.Content?.ToString();
        _settings.Values["EmbeddingDimensions"] = item.Tag?.ToString();
        PrepareEmbeddingsButton.IsEnabled = !_busy;
    }

    private void CompletionModel_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ModelsComboBox.SelectedItem is string model)
            _settings.Values["CompletionModel"] = model;
    }

    private async Task RefreshEmbeddingModelsAsync()
    {
        _loadingOptions = true;
        EmbeddingModelCombo.Items.Clear();
        try
        {
            using var response = await _bridge.ListEmbeddingModelsAsync();
            foreach (JsonElement model in response.RootElement.GetProperty("result").GetProperty("models").EnumerateArray())
            {
                string name = model.GetProperty("name").GetString() ?? "";
                int dimensions = model.GetProperty("dimensions").GetInt32();
                EmbeddingModelCombo.Items.Add(new ComboBoxItem { Content = name, Tag = dimensions.ToString() });
            }
            string? selected = _settings.Values["EmbeddingModel"] as string;
            EmbeddingModelCombo.SelectedItem = EmbeddingModelCombo.Items
                .OfType<ComboBoxItem>().FirstOrDefault(item => (string?)item.Content == selected)
                ?? EmbeddingModelCombo.Items.OfType<ComboBoxItem>().FirstOrDefault();
            if (EmbeddingModelCombo.SelectedItem is ComboBoxItem chosen)
                _settings.Values["EmbeddingDimensions"] = chosen.Tag?.ToString();
            EmbeddingStatus.Text = EmbeddingModelCombo.Items.Count == 0
                ? T("Установленная embedding-модель Ollama не найдена. Лексический поиск доступен.",
                    "No installed Ollama embedding model was found. Lexical search remains available.")
                : $"{T("Доступно embedding-моделей", "Available embedding models")}: {EmbeddingModelCombo.Items.Count}";
        }
        catch (Exception ex)
        {
            OllamaStatus.Text = T("Семантические модели недоступны; лексический поиск продолжает работать. ",
                "Embedding models are unavailable; lexical search remains available. ") + ex.Message;
        }
        finally
        {
            _loadingOptions = false;
            EmbeddingModelCombo.IsEnabled = SearchModeCombo.SelectedIndex != 0;
            PrepareEmbeddingsButton.IsEnabled = SelectedEmbedding() is not null;
        }
    }

    private PythonBridgeService.EmbeddingProfile? SelectedEmbedding()
    {
        if (EmbeddingModelCombo.SelectedItem is not ComboBoxItem item ||
            !int.TryParse(item.Tag?.ToString(), out int dimensions)) return null;
        return new PythonBridgeService.EmbeddingProfile(item.Content?.ToString() ?? "", dimensions);
    }

    private async Task RefreshModelsAsync()
    {
        try
        {
            using var response = await _bridge.ListModelsAsync();
            string? previous = _settings.Values["CompletionModel"] as string;
            ModelsComboBox.Items.Clear();
            foreach (JsonElement model in response.RootElement.GetProperty("result").GetProperty("models").EnumerateArray())
                if (model.GetString() is string name) ModelsComboBox.Items.Add(name);
            ModelsComboBox.SelectedItem = ModelsComboBox.Items.Contains(previous) ? previous : ModelsComboBox.Items.FirstOrDefault();
            OllamaStatus.Text = ModelsComboBox.Items.Count == 0
                ? T("Ollama доступна, но модели не установлены.", "Ollama is available, but no models are installed.")
                : $"{T("Доступно моделей", "Available models")}: {ModelsComboBox.Items.Count}";
        }
        catch (Exception ex)
        {
            OllamaStatus.Text = T("Ollama недоступна. Лексический поиск работает независимо от неё. ",
                "Ollama is unavailable. Lexical search works without it. ") + ex.Message;
        }
    }

    private void AnswerWebView_NavigationCompleted(WebView2 sender, Microsoft.Web.WebView2.Core.CoreWebView2NavigationCompletedEventArgs args)
    {
        if (!args.IsSuccess) return;
        AnswerWebView.Visibility = Visibility.Visible;
        AnswerText.Visibility = Visibility.Collapsed;
        SetAnswer(AnswerText.Text);
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
        PrepareEmbeddingsButton.Content = T("Подготовить семантический индекс", "Prepare semantic index");
        CancelPreparationButton.Content = T("Отменить", "Cancel");
        if (SearchModeCombo.Items.Count == 3)
        {
            ((ComboBoxItem)SearchModeCombo.Items[0]).Content = T("Лексический", "Lexical");
            ((ComboBoxItem)SearchModeCombo.Items[1]).Content = T("Семантический", "Semantic");
            ((ComboBoxItem)SearchModeCombo.Items[2]).Content = T("Гибридный", "Hybrid");
        }

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

    private async void PrepareEmbeddingsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || SelectedEmbedding() is not PythonBridgeService.EmbeddingProfile embedding) return;
        string[] roots = _storage.Load().Where(path => !string.IsNullOrWhiteSpace(path))
            .Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (roots.Length == 0)
        {
            EmbeddingStatus.Text = T("Сначала добавьте папку в Библиотеку.", "Add a folder in Library first.");
            return;
        }
        _preparation = new CancellationTokenSource();
        SetBusy(true);
        CancelPreparationButton.IsEnabled = true;
        EmbeddingStatus.Text = T("Готовим локальный векторный индекс...", "Preparing the local vector index...");
        var errors = new System.Collections.Generic.List<string>();
        try
        {
            foreach (string root in roots)
            {
                _preparation.Token.ThrowIfCancellationRequested();
                if (!Directory.Exists(root))
                {
                    errors.Add($"{root}: {T("папка недоступна; сохранённый индекс оставлен", "folder unavailable; saved index retained")}");
                    continue;
                }
                try
                {
                    using var response = await _bridge.SyncSourceAsync(root, _preparation.Token,
                        ShowEmbeddingProgress, embedding);
                    JsonElement result = response.RootElement.GetProperty("result");
                    if (result.TryGetProperty("embeddings", out JsonElement report))
                        EmbeddingStatus.Text = $"{T("Готово", "Ready")}: {ReadInt(report, "embedded")} {T("фрагментов подготовлено", "chunks embedded")}, {ReadInt(report, "skipped")} {T("без изменений", "unchanged")}.";
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex) { errors.Add($"{root}: {ex.Message}"); }
            }
            if (errors.Count > 0) EmbeddingStatus.Text = string.Join(Environment.NewLine, errors);
        }
        catch (OperationCanceledException)
        {
            EmbeddingStatus.Text = T("Подготовка отменена; завершённые embeddings и текстовый индекс сохранены.",
                "Preparation cancelled; completed embeddings and the text index were kept.");
        }
        finally
        {
            SetBusy(false);
            CancelPreparationButton.IsEnabled = false;
            _preparation.Dispose();
            _preparation = null;
        }
    }

    private void CancelPreparationButton_Click(object sender, RoutedEventArgs e) => _preparation?.Cancel();

    private void ShowEmbeddingProgress(JsonElement progress)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            string phase = ReadString(progress, "phase", "indexing");
            int current = ReadInt(progress, "current");
            int total = ReadInt(progress, "total");
            EmbeddingStatus.Text = $"{phase}: {current}/{total}";
        });
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
        _lastRoots = Array.Empty<string>();
        ResultsPanel.Children.Clear();
        ResultsExpander.IsExpanded = false;
        ResultsExpander.Visibility = Visibility.Collapsed;
        SearchStatus.Visibility = Visibility.Visible;
        SetAnswer(T("Ожидание результатов поиска...", "Waiting for search results..."));
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
                SetAnswer(T("Нет подключённых документов.", "No documents are connected."));
                return;
            }

            string mode = SearchModeCombo.SelectedItem is ComboBoxItem modeItem
                ? modeItem.Tag?.ToString() ?? "lexical" : "lexical";
            var embedding = mode == "lexical" ? null : SelectedEmbedding();
            if (mode != "lexical" && embedding is null)
                throw new InvalidOperationException(T("Для этого режима выберите установленную embedding-модель в Ollama.",
                    "Choose an installed Ollama embedding model for this search mode."));
            SearchStatus.Text = T("Ищем в сохранённом индексе...", "Searching the saved index...");
            using var response = await _bridge.SearchAsync(roots, query, mode, embedding);

            JsonElement result = response.RootElement.GetProperty("result");
            JsonElement hits = result.GetProperty("hits");

            _lastHits = hits.EnumerateArray()
                .Select(hit => hit.Clone())
                .ToArray();

            _lastQuery = query;
            _lastRoots = roots;
            _lastMode = mode;
            _lastEmbedding = embedding;

            var notices = new System.Collections.Generic.List<string>();
            if (result.TryGetProperty("indexing", out JsonElement indexing) && indexing.GetBoolean())
                notices.Add(T("Индексация ещё не завершена.", "Indexing is still in progress."));
            if (result.TryGetProperty("embedding_pending", out JsonElement pending) && pending.GetBoolean())
                notices.Add(T("Подготовка векторного индекса не завершена; доступны только готовые совпадения.",
                    "The vector index is still being prepared; only ready matches are available."));
            if (result.TryGetProperty("warnings", out JsonElement warnings))
                foreach (JsonElement warning in warnings.EnumerateArray())
                    notices.Add($"⚠ {ReadString(warning, "title", T("Предупреждение документа", "Document warning"))}: {ReadString(warning, "code", "")}");

            if (_lastHits.Length == 0)
            {
                SearchStatus.Text = string.Join(Environment.NewLine, notices.Append(T("Ничего не найдено.", "No results found.")));
                SetAnswer(T("Для генерации ответа нужны найденные материалы.", "Matching documents are required to generate an answer."));
                return;
            }

            ResultsHeading.Text =
                $"{T("Найдено результатов", "Results found")}: {_lastHits.Length}";
            SearchStatus.Visibility = Visibility.Collapsed;
            ResultsExpander.Visibility = Visibility.Visible;

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

                AddResult(hit, title, excerpt, sourceRoot, documentId, score);
            }

            SearchStatus.Text = string.Join(Environment.NewLine, notices);
            SearchStatus.Visibility = notices.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

            SetAnswer(T("Документы найдены. Выберите модель Ollama ", "Documents found. Select an Ollama model ") +
                T("и нажмите «Сгенерировать ответ».", "and click Generate Answer."));
        }
        catch (Exception ex)
        {
            SearchStatus.Text = $"{T("Ошибка поиска", "Search error")}: {ex.Message}";

            SetAnswer(T("Поиск не завершился.", "Search did not complete."));
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
        OllamaStatus.Text = T("Проверяем Ollama...", "Checking Ollama...");
        await RefreshModelsAsync();
        SetBusy(false);
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
        SetAnswer(T("Генерируем ответ. Локальная модель может работать долго...", "Generating an answer. The local model may take some time..."));

        try
        {
            using var response = await _bridge.AnswerAsync(
                model,
                _lastQuery,
                _lastRoots,
                LocalizationService.CurrentLanguage,
                _lastMode,
                _lastEmbedding);

            JsonElement result = response.RootElement.GetProperty("result");
            string answer = result.GetProperty("answer").GetString() ?? T("Модель вернула пустой ответ.", "The model returned an empty answer.");
            var markdown = new System.Text.StringBuilder(answer);
            if (result.TryGetProperty("sources", out JsonElement sources))
            {
                int number = 0;
                foreach (JsonElement source in sources.EnumerateArray())
                {
                    number++;
                    string title = ReadString(source, "title", T("Источник", "Source"));
                    string meta = SourceMetadata(source);
                    markdown.Append($"\n\n**[{number}] {title}** {meta}\n\n{ReadString(source, "excerpt", "")}");
                }
            }
            SetAnswer(markdown.ToString());
        }
        catch (Exception ex)
        {
            SetAnswer($"{T("Поиск сохранён, но ответ получить не удалось", "Search results are still available, but answer generation failed")}: {ex.Message}");
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
        SearchModeCombo.IsEnabled = !busy;
        EmbeddingModelCombo.IsEnabled = !busy && SearchModeCombo.SelectedIndex != 0;
        PrepareEmbeddingsButton.IsEnabled = !busy && SelectedEmbedding() is not null;
        RefreshModelsButton.IsEnabled = !busy;
        ModelsComboBox.IsEnabled = !busy;
        GenerateButton.IsEnabled = !busy &&
            _lastHits.Length > 0 &&
            ModelsComboBox.SelectedItem is string;

        SearchProgress.IsActive = busy;
    }

    private void AddResult(
        JsonElement hit,
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
            MaxLines = 6,
            IsTextSelectionEnabled = true
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
            Text = $"{T("Документ", "Document")}: {documentId} | {T("Оценка", "Score")}: {score:F2} {SourceMetadata(hit)}",
            Opacity = 0.7,
            TextWrapping = TextWrapping.Wrap,
            FontSize = 12
        });

        if (hit.TryGetProperty("full_excerpt", out JsonElement full) &&
            full.ValueKind == JsonValueKind.String && full.GetString() is string fullText && fullText != excerpt)
        {
            card.Children.Add(new Expander
            {
                Header = T("Показать исходный фрагмент", "Show original excerpt"),
                Content = new TextBlock { Text = fullText, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true }
            });
        }

        var openButton = new Button { Content = T("Открыть исходный файл", "Open source file"), HorizontalAlignment = HorizontalAlignment.Left };
        openButton.Click += async (_, _) =>
        {
            try { await OpenSourceAsync(sourceRoot, documentId); }
            catch (Exception ex)
            {
                var dialog = new ContentDialog
                {
                    Title = T("Не удалось открыть файл", "Could not open file"),
                    Content = ex.Message,
                    CloseButtonText = T("Закрыть", "Close"),
                    XamlRoot = XamlRoot
                };
                await dialog.ShowAsync();
            }
        };
        AutomationProperties.SetName(openButton, T("Открыть исходный файл", "Open source file") + ": " + title);
        card.Children.Add(openButton);

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

    private static async Task OpenSourceAsync(string root, string documentId)
    {
        string normalizedRoot = Path.GetFullPath(root);
        string file = Path.GetFullPath(Path.Combine(normalizedRoot, documentId));
        if (!file.StartsWith(normalizedRoot.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar,
                StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("The indexed path is outside its selected folder.");
        var storageFile = await Windows.Storage.StorageFile.GetFileFromPathAsync(file);
        await Windows.System.Launcher.LaunchFileAsync(storageFile);
    }

    private static string SourceMetadata(JsonElement hit)
    {
        var values = new System.Collections.Generic.List<string>();
        if (hit.TryGetProperty("page_number", out JsonElement page) && page.ValueKind == JsonValueKind.Number)
            values.Add($"{T("стр.", "p.")} {page.GetInt32()}");
        string heading = ReadString(hit, "heading", "");
        if (!string.IsNullOrWhiteSpace(heading)) values.Add(heading);
        return values.Count == 0 ? "" : "· " + string.Join(" · ", values);
    }

    private static string ReadString(JsonElement value, string name, string fallback)
    {
        return value.TryGetProperty(name, out JsonElement property) && property.ValueKind == JsonValueKind.String
            ? property.GetString() ?? fallback : fallback;
    }

    private static int ReadInt(JsonElement value, string name) =>
        value.TryGetProperty(name, out JsonElement property) && property.ValueKind == JsonValueKind.Number
            ? property.GetInt32() : 0;

    private async void SetAnswer(string markdown)
    {
        AnswerText.Text = markdown;
        AnswerText.Visibility = Visibility.Visible;
        if (AnswerWebView.Visibility != Visibility.Visible) return;
        bool dark = MainWindow.ActiveWindow?.Content is FrameworkElement root && root.ActualTheme == ElementTheme.Dark;
        string script = $"window.renderStudyContent({JsonSerializer.Serialize(markdown)}, {(dark ? "true" : "false")});";
        try
        {
            await AnswerWebView.ExecuteScriptAsync(script);
            AnswerText.Visibility = Visibility.Collapsed;
        }
        catch
        {
            AnswerWebView.Visibility = Visibility.Collapsed;
            AnswerText.Visibility = Visibility.Visible;
        }
    }
}
