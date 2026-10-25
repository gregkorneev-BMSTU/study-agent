using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
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

            await RefreshSourcesAsync();
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

                int count = source.GetProperty("document_count")
                    .GetInt32();

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
                    Text = $"{count} {LocalizationService.Text("документов", "documents")}",
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

            await RefreshSourcesAsync();
        }
        catch (Exception ex)
        {
            LibraryStatus.Text =
                $"{LocalizationService.Text("Ошибка добавления папки", "Error adding folder")}: {ex.Message}";
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




