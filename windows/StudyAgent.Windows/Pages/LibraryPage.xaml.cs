using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using StudyAgent_Windows.Services;
using Windows.Storage.Pickers;

namespace StudyAgent_Windows.Pages;

public sealed partial class LibraryPage : Page
{
    private readonly PythonBridgeService _bridge = new();
    private readonly LibraryStorageService _storage = new();
    private readonly List<string> _roots = new();
    private bool _busy;
    private bool _initialized;
    private bool _ocrRuntimeAvailable;
    private bool _ocrWeightsInstalled;
    private CancellationTokenSource? _operation;

    public LibraryPage()
    {
        InitializeComponent();
        Loaded += LibraryPage_Loaded;
    }


    private void ApplyLanguage()
    {
        LibraryTitle.Text =
            LocalizationService.Text("Библиотека", "Library");

        LibrarySubtitle.Text =
            LocalizationService.Text(
                "Подключённые учебные материалы",
                "Connected study materials");

        AddFolderLabel.Text =
            LocalizationService.Text("Добавить папку", "Add Folder");
        CheckChangesButton.Content = LocalizationService.Text("Проверить изменения", "Check for Changes");
        CancelIndexButton.Content = LocalizationService.Text("Отменить", "Cancel");
        InstallOcrButton.Content = LocalizationService.Text("Установить веса OCR", "Install OCR weights");

        DiagnoseButton.Content =
            LocalizationService.Text(
                "Проверить Python-backend", "Check Python Backend");

        LibraryStatus.Text =
            LocalizationService.Text(
                LocalizationService.Text("Добавьте папку с учебными материалами.", "Add a folder containing study materials."),
                "Add a folder containing study materials.");
    }

    private async void LibraryPage_Loaded(
        object sender, RoutedEventArgs e)
    {
        ApplyLanguage();
        if (_initialized)
            return;

        _initialized = true;
        ApplyLanguage();

        try
        {
            _roots.Clear();

            foreach (string path in _storage.Load())
            {
                if (!string.IsNullOrWhiteSpace(path) &&
                    !_roots.Exists(existing =>
                        string.Equals(existing, path,
                            StringComparison.OrdinalIgnoreCase)))
                {
                    _roots.Add(path);
                }
            }

        }
        catch (Exception ex)
        {
            LibraryStatus.Text =
                $"{LocalizationService.Text("Ошибка загрузки библиотеки", "Error loading library")}: {ex.Message}";
        }
    }

    private async Task RefreshSourcesAsync()
    {
        if (_busy)
            return;

        _busy = true;
        AddFolderButton.IsEnabled = false;
        LoadingIndicator.IsActive = true;

        try
        {
            SourcesList.Items.Clear();

            if (_roots.Count == 0)
            {
                LibraryStatus.Text =
                    LocalizationService.Text("Добавьте папку с учебными материалами.", "Add a folder containing study materials.");
                return;
            }

            LibraryStatus.Text = LocalizationService.Text("Обновляем библиотеку...", "Refreshing library...");

            using var response =
                await _bridge.ListSourcesAsync(_roots.ToArray());

            JsonElement sources = response.RootElement
                .GetProperty("result")
                .GetProperty("sources");

            foreach (JsonElement source in sources.EnumerateArray())
            {
                string name = source.GetProperty("name")
                    .GetString() ?? LocalizationService.Text("Без названия", "Untitled");

                string path = source.GetProperty("path")
                    .GetString() ?? "";

                int count = source.GetProperty("document_count").GetInt32();
                bool available = !source.TryGetProperty("available", out JsonElement availableValue) ||
                    availableValue.GetBoolean();
                string state = available
                    ? LocalizationService.Text("Доступна", "Available")
                    : LocalizationService.Text("Папка сейчас недоступна; используется сохранённый индекс", "Folder is unavailable; saved index is used");
                string detail = $"{state} · {count} {LocalizationService.Text("документов", "documents")}";

                try
                {
                    using var statusResponse = await _bridge.IndexStatusAsync(path);
                    JsonElement index = statusResponse.RootElement.GetProperty("result");
                    int chunks = ReadInt(index, "chunks");
                    string last = ReadString(index, "last_indexed_at");
                    detail += $" · {ReadInt(index, "ready")}/{ReadInt(index, "documents")} {LocalizationService.Text("готово", "ready")}, {ReadInt(index, "partial")} {LocalizationService.Text("частично", "partial")}, {ReadInt(index, "failed")} {LocalizationService.Text("ошибок", "failed")} · {chunks} {LocalizationService.Text("фрагментов", "chunks")}";
                    if (!string.IsNullOrWhiteSpace(last))
                        detail += $" · {LocalizationService.Text("обновлено", "updated")}: {last}";
                    if (index.TryGetProperty("issues", out JsonElement issues) && issues.GetArrayLength() > 0)
                    {
                        detail += $" · ⚠ {issues.GetArrayLength()} {LocalizationService.Text("предупреждений", "warnings")}";
                        foreach (JsonElement issue in issues.EnumerateArray())
                        {
                            string issueTitle = ReadString(issue, "title");
                            if (string.IsNullOrWhiteSpace(issueTitle)) issueTitle = ReadString(issue, "document_id");
                            detail += $"\n⚠ {issueTitle}: {ReadString(issue, "code")}";
                        }
                    }
                }
                catch (Exception ex)
                {
                    detail += $" · {ex.Message}";
                }

                var title = new TextBlock
                {
                    Text = name,
                    FontSize = 18,
                    FontWeight = new Windows.UI.Text.FontWeight
                    {
                        Weight = 600
                    }
                };

                var details = new TextBlock
                {
                    Text = detail,
                    Opacity = 0.75
                };

                var pathText = new TextBlock
                {
                    Text = path,
                    TextWrapping = TextWrapping.Wrap,
                    Opacity = 0.75
                };

                var removeButton = new Button
                {
                    Content = LocalizationService.Text("Отключить", "Remove"),
                    Tag = path,
                    HorizontalAlignment = HorizontalAlignment.Left
                };

                removeButton.Click += RemoveFolderButton_Click;

                var card = new StackPanel
                {
                    Spacing = 7,
                    Padding = new Thickness(12)
                };

                card.Children.Add(title);
                card.Children.Add(details);
                card.Children.Add(pathText);
                card.Children.Add(removeButton);

                var item = new ListViewItem
                {
                    Content = card,
                    HorizontalContentAlignment =
                        HorizontalAlignment.Stretch
                };

                SourcesList.Items.Add(item);
            }

            LibraryStatus.Text =
                $"{LocalizationService.Text("Подключено папок", "Connected folders")}: {_roots.Count}";
        }
        catch (Exception ex)
        {
            LibraryStatus.Text =
                $"{LocalizationService.Text("Не удалось обновить библиотеку", "Could not refresh library")}: {ex.Message}";
        }
        finally
        {
            _busy = false;
            AddFolderButton.IsEnabled = true;
            LoadingIndicator.IsActive = false;
        }
    }

    public void RequestAddFolder() =>
        AddFolderButton_Click(AddFolderButton, new RoutedEventArgs());

    private async void AddFolderButton_Click(
        object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;

        try
        {
            var window = MainWindow.ActiveWindow
                ?? throw new InvalidOperationException(
                    LocalizationService.Text("Главное окно недоступно.", "Main window is unavailable."));

            var picker = new FolderPicker();
            picker.FileTypeFilter.Add("*");

            var hwnd = WinRT.Interop.WindowNative
                .GetWindowHandle(window);

            WinRT.Interop.InitializeWithWindow.Initialize(
                picker, hwnd);

            var folder = await picker.PickSingleFolderAsync();

            if (folder is null)
                return;

            if (_roots.Exists(path =>
                string.Equals(path, folder.Path,
                    StringComparison.OrdinalIgnoreCase)))
            {
                LibraryStatus.Text =
                    LocalizationService.Text("Эта папка уже подключена.", "This folder is already connected.");
                return;
            }

            if (!Directory.Exists(folder.Path))
            {
                LibraryStatus.Text =
                    LocalizationService.Text("Выбранная папка недоступна.", "The selected folder is unavailable.");
                return;
            }

            var updatedRoots = new List<string>(_roots)
            {
                folder.Path
            };

            _storage.Save(updatedRoots);
            _roots.Clear();
            _roots.AddRange(updatedRoots);
            _operation = new CancellationTokenSource();
            SetIndexing(true);
            LibraryStatus.Text = LocalizationService.Text("Индексируем новую папку...", "Indexing the new folder...");
            using (var indexResponse = await _bridge.SyncSourceAsync(folder.Path, _operation.Token, ShowProgress))
            {
                JsonElement result = indexResponse.RootElement.GetProperty("result");
                if (result.TryGetProperty("cancelled", out JsonElement cancelled) && cancelled.GetBoolean())
                    LibraryStatus.Text = LocalizationService.Text("Индексация отменена. Её можно повторить.", "Indexing cancelled. You can retry it.");
                else
                    LibraryStatus.Text = FormatIndexResult(result);
            }
        }
        catch (Exception ex)
        {
            LibraryStatus.Text =
                $"{LocalizationService.Text("Ошибка добавления папки", "Error adding folder")}: {ex.Message}";
        }
        finally
        {
            SetIndexing(false);
            _operation?.Dispose();
            _operation = null;
            await RefreshSourcesAsync();
        }
    }

    private async void RemoveFolderButton_Click(
        object sender, RoutedEventArgs e)
    {
        if (_busy || sender is not Button button ||
            button.Tag is not string path)
        {
            return;
        }

        try
        {
            using var removeResponse = await _bridge.RemoveIndexSourceAsync(path);
            var updatedRoots = new List<string>(_roots);

            updatedRoots.RemoveAll(existing =>
                string.Equals(existing, path,
                    StringComparison.OrdinalIgnoreCase));

            _storage.Save(updatedRoots);

            _roots.Clear();
            _roots.AddRange(updatedRoots);

            await RefreshSourcesAsync();
        }
        catch (Exception ex)
        {
            LibraryStatus.Text =
                $"{LocalizationService.Text("Ошибка отключения папки", "Error removing folder")}: {ex.Message}";
        }
    }

    private async void CheckChangesButton_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _roots.Count == 0) return;
        _operation = new CancellationTokenSource();
        SetIndexing(true);
        var reports = new List<string>();
        try
        {
            foreach (string root in _roots)
            {
                _operation.Token.ThrowIfCancellationRequested();
                if (!Directory.Exists(root))
                {
                    reports.Add($"{root}: {LocalizationService.Text("недоступна, сохранённый индекс оставлен", "unavailable; saved index kept")}");
                    continue;
                }
                try
                {
                    using var response = await _bridge.SyncSourceAsync(
                        root, _operation.Token, ShowProgress, verifyHash: true);
                    reports.Add(FormatIndexResult(response.RootElement.GetProperty("result")));
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex) { reports.Add($"{root}: {ex.Message}"); }
            }
            LibraryStatus.Text = reports.Count == 0
                ? LocalizationService.Text("Нет доступных папок для проверки.", "No available folders to check.")
                : string.Join(Environment.NewLine, reports);
        }
        catch (OperationCanceledException)
        {
            LibraryStatus.Text = LocalizationService.Text("Индексация отменена. Незавершённые источники можно проверить повторно.", "Indexing cancelled. Incomplete sources can be checked again.");
        }
        finally
        {
            SetIndexing(false);
            _operation.Dispose();
            _operation = null;
            await RefreshSourcesAsync();
        }
    }

    private void CancelIndexButton_Click(object sender, RoutedEventArgs e) => _operation?.Cancel();

    private async void InstallOcrButton_Click(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        _operation = new CancellationTokenSource();
        SetIndexing(true);
        OcrProgress.IsActive = true;
        InstallOcrButton.IsEnabled = false;
        LibraryStatus.Text = LocalizationService.Text("Установка весов OCR запущена по вашему запросу...", "Installing OCR weights at your request...");
        try
        {
            using var response = await _bridge.InstallOcrModelAsync(_operation.Token, ShowProgress);
            _ocrWeightsInstalled = true;
            InstallOcrButton.Content = LocalizationService.Text("Веса OCR установлены", "OCR weights installed");
            LibraryStatus.Text = LocalizationService.Text("Веса OCR установлены.", "OCR weights installed.");
        }
        catch (OperationCanceledException)
        {
            LibraryStatus.Text = LocalizationService.Text("Установка весов OCR отменена.", "OCR weight installation cancelled.");
        }
        catch (Exception ex)
        {
            LibraryStatus.Text = $"{LocalizationService.Text("Не удалось установить веса OCR", "Could not install OCR weights")}: {ex.Message}";
        }
        finally
        {
            OcrProgress.IsActive = false;
            InstallOcrButton.IsEnabled = true;
            SetIndexing(false);
            _operation.Dispose();
            _operation = null;
        }
    }

    private void SetIndexing(bool active)
    {
        _busy = active;
        AddFolderButton.IsEnabled = !active;
        CheckChangesButton.IsEnabled = !active;
        CancelIndexButton.IsEnabled = active;
        InstallOcrButton.IsEnabled = !active && _ocrRuntimeAvailable && !_ocrWeightsInstalled;
        IndexProgress.Visibility = active ? Visibility.Visible : Visibility.Collapsed;
        LoadingIndicator.IsActive = active;
    }

    private void ShowProgress(JsonElement progress)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            int current = ReadInt(progress, "current");
            int total = ReadInt(progress, "total");
            IndexProgress.Value = total > 0 ? 100.0 * current / total : 0;
            string phase = ReadString(progress, "phase");
            LibraryStatus.Text = $"{phase} · {current}/{total} · {ReadInt(progress, "indexed")} {LocalizationService.Text("готово", "ready")} · {ReadInt(progress, "failed")} {LocalizationService.Text("ошибок", "errors")}";
        });
    }

    private string FormatIndexResult(JsonElement result)
    {
        string summary = $"{LocalizationService.Text("Готово", "Done")}: {ReadInt(result, "indexed")} {LocalizationService.Text("обработано", "indexed")}, {ReadInt(result, "skipped")} {LocalizationService.Text("без изменений", "unchanged")}, {ReadInt(result, "failed")} {LocalizationService.Text("ошибок", "errors")}.";
        if (result.TryGetProperty("errors", out JsonElement errors) && errors.GetArrayLength() > 0)
            summary += Environment.NewLine + string.Join(Environment.NewLine, errors.EnumerateArray().Select(issue => $"⚠ {ReadString(issue, "document_id")}: {ReadString(issue, "code")}"));
        return summary;
    }

    private static int ReadInt(JsonElement value, string name) =>
        value.TryGetProperty(name, out JsonElement property) && property.ValueKind == JsonValueKind.Number ? property.GetInt32() : 0;

    private static string ReadString(JsonElement value, string name) =>
        value.TryGetProperty(name, out JsonElement property) && property.ValueKind == JsonValueKind.String ? property.GetString() ?? "" : "";

    private async void DiagnoseButton_Click(
        object sender, RoutedEventArgs e)
    {
        DiagnoseButton.IsEnabled = false;
        DiagnoseButton.Content = LocalizationService.Text("Проверка выполняется...", "Checking...");
        BackendStatus.Text = LocalizationService.Text("Запрос отправлен. Ожидаем ответ backend...", "Request sent. Waiting for backend...");

        try
        {
            using var response = await _bridge.DiagnoseAsync();

            JsonElement data = response.RootElement
                .GetProperty("result");

            BackendStatus.Text =
                "Backend: " +
                (data.GetProperty("backend_healthy").GetBoolean()
                    ? LocalizationService.Text("Работает", "Working") : LocalizationService.Text("Ошибка", "Error")) +
                "\nPDF: " +
                (data.GetProperty("pdf_available").GetBoolean()
                    ? LocalizationService.Text("Доступен", "Available") : LocalizationService.Text("Недоступен", "Unavailable")) +
                "\nOCR: " +
                (data.GetProperty("ocr_runtime_available").GetBoolean()
                    ? LocalizationService.Text("Доступен", "Available") : LocalizationService.Text("Не установлен", "Not installed"));
            BackendStatus.Text += "\n" + SystemInfoService.Summary();
            bool ocrRuntime = data.GetProperty("ocr_runtime_available").GetBoolean();
            string weights = data.TryGetProperty("ocr_weights_state", out JsonElement weightState)
                ? weightState.GetString() ?? "unknown" : "unknown";
            BackendStatus.Text += "\n" + LocalizationService.Text("Веса OCR", "OCR weights") + ": " +
                (weights == "installed" ? LocalizationService.Text("установлены", "installed") : LocalizationService.Text("не установлены", "not installed"));
            bool weightsInstalled = weights == "installed";
            _ocrRuntimeAvailable = ocrRuntime;
            _ocrWeightsInstalled = weightsInstalled;
            InstallOcrButton.IsEnabled = ocrRuntime && !weightsInstalled;
            if (weightsInstalled)
                InstallOcrButton.Content = LocalizationService.Text("Веса OCR установлены", "OCR weights installed");
            if (!ocrRuntime)
                BackendStatus.Text += "\n" + LocalizationService.Text("OCR-обработка недоступна в этом пакете.", "OCR processing is unavailable in this package.");
            try
            {
                using var modelsResponse = await _bridge.ListModelsAsync();
                JsonElement models = modelsResponse.RootElement.GetProperty("result").GetProperty("models");
                BackendStatus.Text += "\nOllama: " + (models.GetArrayLength() > 0
                    ? $"{LocalizationService.Text("установлено моделей", "models installed")}: {models.GetArrayLength()}"
                    : LocalizationService.Text("модели не установлены", "no models installed"));
            }
            catch
            {
                BackendStatus.Text += "\nOllama: " + LocalizationService.Text("недоступна", "unavailable");
            }
        }
        catch (Exception ex)
        {
            BackendStatus.Text =
                $"{LocalizationService.Text("Ошибка диагностики", "Diagnostic error")}: {ex.Message}";
        }
        finally
        {
            DiagnoseButton.IsEnabled = true;
            DiagnoseButton.Content = LocalizationService.Text("Проверить Python-backend", "Check Python Backend");

            var dialog = new ContentDialog
            {
                Title = LocalizationService.Text("Результат диагностики", "Diagnostic Results"),
                Content = BackendStatus.Text,
                CloseButtonText = LocalizationService.Text("Закрыть", "Close"),
                XamlRoot = this.XamlRoot
            };

            await dialog.ShowAsync();
        }
    }
}




