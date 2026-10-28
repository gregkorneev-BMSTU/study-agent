using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Windows.Storage;

namespace StudyAgent_Windows.Services;

public sealed class PythonBridgeService
{
    private static readonly object BackendExtractLock = new();
    private static readonly ConcurrentDictionary<int, Process> ActiveProcesses = new();

    public static void TerminateAll()
    {
        foreach (Process process in ActiveProcesses.Values)
        {
            try
            {
                if (!process.HasExited) process.Kill(entireProcessTree: true);
            }
            catch (System.ComponentModel.Win32Exception) { }
            catch (InvalidOperationException) { }
        }
    }

    public sealed record EmbeddingProfile(string Model, int Dimensions,
        string DocumentPrefix = "", string QueryPrefix = "");

    private static string EnsureArchivedBackend()
    {
        string archive = Path.Combine(AppContext.BaseDirectory, "Backend.zip");
        using var stream = File.OpenRead(archive);
        string digest = Convert.ToHexString(SHA256.HashData(stream))[..16];
        string cacheRoot = Path.Combine(ApplicationData.Current.LocalFolder.Path, "backend-cache");
        string destination = Path.Combine(cacheRoot, digest);
        string executable = Path.Combine(destination, "StudyAgentBackend.exe");

        lock (BackendExtractLock)
        {
            if (File.Exists(executable) && File.Exists(Path.Combine(destination, ".ready")))
                return executable;

            Directory.CreateDirectory(cacheRoot);
            string temporary = Path.Combine(cacheRoot, digest + ".extracting");
            if (Directory.Exists(temporary)) Directory.Delete(temporary, recursive: true);
            ZipFile.ExtractToDirectory(archive, temporary);
            if (!File.Exists(Path.Combine(temporary, "StudyAgentBackend.exe")))
            {
                Directory.Delete(temporary, recursive: true);
                throw new FileNotFoundException("StudyAgentBackend.exe is missing from Backend.zip");
            }

            File.WriteAllText(Path.Combine(temporary, ".ready"), "ready");
            if (Directory.Exists(destination)) Directory.Delete(destination, recursive: true);
            Directory.Move(temporary, destination);
        }
        return executable;
    }

    public Task<JsonDocument> DiagnoseAsync(CancellationToken token = default) =>
        SendAsync(Request("diagnose_backend"), cancellationToken: token);

    public Task<JsonDocument> ListSourcesAsync(string[] roots, CancellationToken token = default) =>
        SendAsync(Request("list_sources", ("roots", roots)), cancellationToken: token);

    public Task<JsonDocument> SyncSourceAsync(string root, CancellationToken token = default,
        Action<JsonElement>? progress = null, EmbeddingProfile? embedding = null, bool verifyHash = false) =>
        SendAsync(Request("sync_source", ("root", root),
            ("embedding", embedding is null ? null : Embedding(embedding)),
            ("verify_hash", verifyHash ? true : null)), 3600, token, progress);

    public Task<JsonDocument> IndexStatusAsync(string root, EmbeddingProfile? embedding = null,
        CancellationToken token = default) =>
        SendAsync(Request("index_status", ("root", root), ("embedding", embedding is null ? null : Embedding(embedding))), cancellationToken: token);

    public Task<JsonDocument> RemoveIndexSourceAsync(string root, CancellationToken token = default) =>
        SendAsync(Request("remove_index_source", ("root", root)), cancellationToken: token);

    public Task<JsonDocument> SearchAsync(string[] roots, string query, string mode,
        EmbeddingProfile? embedding = null, CancellationToken token = default,
        Action<JsonElement>? progress = null) =>
        SendAsync(Request("search", ("roots", roots), ("query", query), ("search_mode", mode),
            ("embedding", embedding is null ? null : Embedding(embedding))), 240, token, progress);

    public Task<JsonDocument> ListModelsAsync(CancellationToken token = default) =>
        SendAsync(Request("list_models"), cancellationToken: token);

    public Task<JsonDocument> ListEmbeddingModelsAsync(CancellationToken token = default) =>
        SendAsync(Request("list_embedding_models"), cancellationToken: token);

    public Task<JsonDocument> InstallOcrModelAsync(CancellationToken token = default,
        Action<JsonElement>? progress = null) =>
        SendAsync(Request("install_ocr_model"), 3600, token, progress);

    public Task<JsonDocument> AnswerAsync(string model, string query, string[] roots,
        string language, string mode, EmbeddingProfile? embedding = null,
        CancellationToken token = default) =>
        SendAsync(Request("answer", ("model", model), ("query", query), ("roots", roots),
            ("language", language), ("search_mode", mode),
            ("embedding", embedding is null ? null : Embedding(embedding))), 240, token);

    private static object Embedding(EmbeddingProfile profile) => new
    {
        model = profile.Model,
        dimensions = profile.Dimensions,
        document_prefix = profile.DocumentPrefix,
        query_prefix = profile.QueryPrefix
    };

    private static Dictionary<string, object?> Request(string command,
        params (string Name, object? Value)[] values)
    {
        var request = new Dictionary<string, object?>
        {
            ["request_id"] = Guid.NewGuid().ToString(),
            ["command"] = command
        };
        foreach (var (name, value) in values)
            if (value is not null) request[name] = value;
        return request;
    }

    private static async Task<JsonDocument> SendAsync(object request, int timeoutSeconds = 30,
        CancellationToken cancellationToken = default, Action<JsonElement>? progress = null)
    {
        string bundledPath = Path.Combine(AppContext.BaseDirectory, "Backend", "StudyAgentBackend.exe");
        string? root = null;
        string backendPath;
        bool packaged;

        if (File.Exists(bundledPath))
        {
            backendPath = bundledPath;
            packaged = true;
        }
        else if (File.Exists(Path.Combine(AppContext.BaseDirectory, "Backend.zip")))
        {
            backendPath = EnsureArchivedBackend();
            packaged = true;
        }
        else
        {
            root = FindRepositoryRoot();
            string localBackend = Path.Combine(root, "build", "windows-backend", "dist",
                "StudyAgentBackend", "StudyAgentBackend.exe");
            packaged = File.Exists(localBackend);
            backendPath = packaged ? localBackend : Path.Combine(root, ".venv", "Scripts", "python.exe");
        }

        if (!File.Exists(backendPath))
            throw new FileNotFoundException(LocalizationService.Text(
                "Не найден упакованный backend. Переустановите приложение или соберите пакет.",
                "The packaged backend is missing. Reinstall the app or rebuild the package."), backendPath);

        var info = new ProcessStartInfo
        {
            FileName = backendPath,
            Arguments = packaged ? "" : "-X utf8 -m study_agent.mac_bridge",
            WorkingDirectory = packaged ? Path.GetDirectoryName(backendPath)! : root!,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false),
            StandardOutputEncoding = new UTF8Encoding(false),
            StandardErrorEncoding = new UTF8Encoding(false)
        };
        info.Environment["PYTHONIOENCODING"] = "utf-8";
        info.Environment["PYTHONUTF8"] = "1";
        info.Environment["STUDY_AGENT_DATA_DIR"] = Path.Combine(ApplicationData.Current.LocalFolder.Path, "StudyAgent");

        using var process = new Process { StartInfo = info };
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(timeout.Token, cancellationToken);
        bool started = false;
        try
        {
            try
            {
                if (!process.Start()) throw new InvalidOperationException("Backend process did not start.");
            }
            catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException)
            {
                throw new InvalidOperationException(LocalizationService.Text(
                    "Не удалось запустить локальный backend.", "Could not start the local backend."), ex);
            }
            started = true;
            ActiveProcesses[process.Id] = process;
            Task<string> errorTask = process.StandardError.ReadToEndAsync(linked.Token);
            string requestId = ((Dictionary<string, object?>)request)["request_id"]!.ToString()!;
            await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(request).AsMemory(), linked.Token);
            await process.StandardInput.FlushAsync(linked.Token);
            process.StandardInput.Close();

            string? response = null;
            string? line;
            while ((line = await process.StandardOutput.ReadLineAsync(linked.Token)) is not null)
            {
                using var message = JsonDocument.Parse(line);
                JsonElement payload = message.RootElement;
                if (payload.TryGetProperty("event", out JsonElement eventType) &&
                    eventType.GetString() == "progress")
                {
                    if (payload.TryGetProperty("request_id", out JsonElement eventId) &&
                        eventId.GetString() == requestId && payload.TryGetProperty("result", out JsonElement data))
                        progress?.Invoke(data.Clone());
                    continue;
                }
                if (payload.TryGetProperty("request_id", out JsonElement responseId) &&
                    responseId.GetString() != requestId)
                    continue;
                response = line;
            }

            await process.WaitForExitAsync(linked.Token);
            string errors = await errorTask;
            if (process.ExitCode != 0)
                throw new InvalidOperationException($"Backend exited with code {process.ExitCode}: {errors}");
            if (string.IsNullOrWhiteSpace(response))
                throw new InvalidOperationException(LocalizationService.Text(
                    "Backend завершился без ответа.", "Backend exited without a response."));

            JsonDocument document = JsonDocument.Parse(response);
            if (!document.RootElement.TryGetProperty("ok", out JsonElement ok) || ok.ValueKind != JsonValueKind.True)
            {
                JsonElement error = document.RootElement.TryGetProperty("error", out JsonElement e) ? e : default;
                string code = error.ValueKind == JsonValueKind.Object && error.TryGetProperty("code", out JsonElement c)
                    ? c.GetString() ?? "backend_error" : "backend_error";
                string message = error.ValueKind == JsonValueKind.Object && error.TryGetProperty("message", out JsonElement m)
                    ? m.GetString() ?? code : code;
                document.Dispose();
                throw new InvalidOperationException($"[{code}] {message}");
            }
            return document;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested)
        {
            throw new TimeoutException(LocalizationService.Text(
                $"Backend не ответил за {timeoutSeconds} секунд.",
                $"Backend did not respond within {timeoutSeconds} seconds."));
        }
        finally
        {
            if (started) ActiveProcesses.TryRemove(process.Id, out _);
            if (started && !process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                await process.WaitForExitAsync();
            }
        }
    }

    private static string FindRepositoryRoot()
    {
        DirectoryInfo? directory = new(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "pyproject.toml"))) return directory.FullName;
            directory = directory.Parent;
        }
        throw new DirectoryNotFoundException("Study Agent repository root was not found.");
    }
}
