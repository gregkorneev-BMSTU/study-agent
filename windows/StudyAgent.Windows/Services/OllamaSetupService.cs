using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace StudyAgent_Windows.Services;

public sealed class OllamaSetupService
{
    private static readonly HttpClient Client = new() { Timeout = Timeout.InfiniteTimeSpan };
    public const string RecommendedModel = "qwen3.5:4b";

    public async Task PullRecommendedAsync(IProgress<(string Status, long? Completed, long? Total)> progress,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "http://127.0.0.1:11434/api/pull")
        {
            Content = new StringContent(JsonSerializer.Serialize(new { model = RecommendedModel, stream = true }),
                Encoding.UTF8, "application/json")
        };
        using var response = await Client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException($"Ollama returned HTTP {(int)response.StatusCode}.");
        await using Stream stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var reader = new StreamReader(stream, Encoding.UTF8);
        bool succeeded = false;
        while (await reader.ReadLineAsync(cancellationToken) is string line)
        {
            cancellationToken.ThrowIfCancellationRequested();
            using JsonDocument message = JsonDocument.Parse(line);
            JsonElement value = message.RootElement;
            if (value.TryGetProperty("error", out JsonElement error))
                throw new InvalidOperationException(error.GetString() ?? "Ollama model download failed.");
            string status = value.TryGetProperty("status", out JsonElement statusValue)
                ? statusValue.GetString() ?? "" : "";
            long? completed = value.TryGetProperty("completed", out JsonElement done) && done.TryGetInt64(out long d) ? d : null;
            long? total = value.TryGetProperty("total", out JsonElement length) && length.TryGetInt64(out long t) ? t : null;
            progress.Report((status, completed, total));
            if (status == "success") succeeded = true;
        }
        if (!succeeded) throw new InvalidOperationException("Ollama closed the download stream before reporting success.");
    }
}
