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

    private async void LibraryPage_Loaded(
        object sender, RoutedEventArgs e)
    {
        if (_initialized)
            return;

        _initialized = true;

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
                $"Ошибка загрузки библиотеки: {ex.Message}";
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
                    "Добавьте папку с учебными материалами.";
                return;
            }

            LibraryStatus.Text = "Обновляем библиотеку...";

            using var response =
                await _bridge.ListSourcesAsync(_roots.ToArray());

            JsonElement sources = response.RootElement
                .GetProperty("result")
                .GetProperty("sources");

            foreach (JsonElement source in sources.EnumerateArray())
            {
                string name = source.GetProperty("name")
                    .GetString() ?? "Без названия";

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
                    Text = $"{count} документов",
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
                    Content = "Отключить",
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
                $"Подключено папок: {_roots.Count}";
        }
        catch (Exception ex)
        {
            LibraryStatus.Text =
                $"Не удалось обновить библиотеку: {ex.Message}";
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
                    "Главное окно недоступно.");

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
                    "Эта папка уже подключена.";
                return;
            }

            if (!Directory.Exists(folder.Path))
            {
                LibraryStatus.Text =
                    "Выбранная папка недоступна.";
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
                $"Ошибка добавления папки: {ex.Message}";
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
                $"Ошибка отключения папки: {ex.Message}";
        }
    }

    private async void DiagnoseButton_Click(
        object sender, RoutedEventArgs e)
    {
        DiagnoseButton.IsEnabled = false;
        BackendStatus.Text = "Проверяем backend...";

        try
        {
            using var response = await _bridge.DiagnoseAsync();

            JsonElement data = response.RootElement
                .GetProperty("result");

            BackendStatus.Text =
                "Backend: " +
                (data.GetProperty("backend_healthy").GetBoolean()
                    ? "Работает" : "Ошибка") +
                "\nPDF: " +
                (data.GetProperty("pdf_available").GetBoolean()
                    ? "Доступен" : "Недоступен") +
                "\nOCR: " +
                (data.GetProperty("ocr_runtime_available").GetBoolean()
                    ? "Доступен" : "Не установлен");
        }
        catch (Exception ex)
        {
            BackendStatus.Text =
                $"Ошибка диагностики: {ex.Message}";
        }
        finally
        {
            DiagnoseButton.IsEnabled = true;
        }
    }
}
