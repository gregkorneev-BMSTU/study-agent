using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using StudyAgent_Windows.Services;

namespace StudyAgent_Windows.Pages;

public sealed partial class LibraryPage : Page
{
    private readonly PythonBridgeService _bridge = new();

    public LibraryPage()
    {
        InitializeComponent();

        var button = new Button
        {
            Content = "Проверить Python-backend",
            Margin = new Thickness(32, 20, 0, 0),
            HorizontalAlignment = HorizontalAlignment.Left
        };

        var result = new TextBlock
        {
            Text = "Backend ещё не проверен",
            Margin = new Thickness(32, 70, 20, 0),
            TextWrapping = TextWrapping.Wrap
        };

        if (Content is Grid grid &&
            grid.Children.Count > 0 &&
            grid.Children[0] is StackPanel panel)
        {
            panel.Children.Add(button);
            panel.Children.Add(result);
        }

        button.Click += async (_, _) =>
        {
            button.IsEnabled = false;
            result.Text = "Проверяем Python-backend...";

            try
            {
                using var response = await _bridge.DiagnoseAsync();
                var data = response.RootElement.GetProperty("result");

                bool healthy = data
                    .GetProperty("backend_healthy")
                    .GetBoolean();

                bool pdf = data
                    .GetProperty("pdf_available")
                    .GetBoolean();

                bool ocr = data
                    .GetProperty("ocr_runtime_available")
                    .GetBoolean();

                result.Text =
                    $"Backend: {(healthy ? "Работает" : "Ошибка")}\n" +
                    $"PDF: {(pdf ? "Доступен" : "Недоступен")}\n" +
                    $"OCR: {(ocr ? "Доступен" : "Не установлен")}";
            }
            catch (Exception ex)
            {
                result.Text = $"Ошибка подключения: {ex.Message}";
            }
            finally
            {
                button.IsEnabled = true;
            }
        };
    }
}
