using System.Globalization;
using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace StudyAgent_Windows.Controls;

/// <summary>
/// Renders untrusted Markdown/LaTeX through the packaged offline viewer. The WebView2 is created
/// only on <see cref="Activate"/>; until it succeeds the plain selectable text stays visible.
/// </summary>
public sealed class RenderedMarkdownView : Grid
{
    private const double ViewMinHeight = 48;
    private const double ViewMaxHeight = 640;

    private readonly string _markdown;
    private readonly TextBlock _fallback;
    private WebView2? _web;

    public RenderedMarkdownView(string markdown)
    {
        _markdown = markdown;
        _fallback = new TextBlock { Text = markdown, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        Children.Add(_fallback);
    }

    public void Activate()
    {
        if (_web is not null) return;
        _web = new WebView2 { Height = ViewMinHeight, Visibility = Visibility.Collapsed };
        _web.NavigationCompleted += async (_, args) =>
        {
            if (args.IsSuccess) await RenderAsync();
        };
        Children.Add(_web);
        _web.Source = new Uri(Path.Combine(AppContext.BaseDirectory, "assets", "math", "index.html"));
    }

    private async Task RenderAsync()
    {
        if (_web is null) return;
        bool dark = ActualTheme == ElementTheme.Dark;
        try
        {
            await _web.ExecuteScriptAsync(
                $"window.renderStudyContent({JsonSerializer.Serialize(_markdown)}, {(dark ? "true" : "false")});");
            string measured = await _web.ExecuteScriptAsync("document.documentElement.scrollHeight");
            if (double.TryParse(measured.Trim('"'), NumberStyles.Float, CultureInfo.InvariantCulture, out double height))
                _web.Height = Math.Clamp(height + 8, ViewMinHeight, ViewMaxHeight);
            _web.Visibility = Visibility.Visible;
            _fallback.Visibility = Visibility.Collapsed;
        }
        catch
        {
            _web.Visibility = Visibility.Collapsed;
            _fallback.Visibility = Visibility.Visible;
        }
    }
}
