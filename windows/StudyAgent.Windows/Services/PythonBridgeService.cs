using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace StudyAgent_Windows.Services;

public sealed class PythonBridgeService
{
    public Task<JsonDocument> DiagnoseAsync()
    {
        return SendAsync(new
        {
            request_id = Guid.NewGuid().ToString(),
            command = "diagnose_backend"
        });
    }

    public Task<JsonDocument> ListSourcesAsync(
        string[] roots)
    {
        return SendAsync(new
        {
            request_id = Guid.NewGuid().ToString(),
            command = "list_sources",
            roots
        });
    }

    public Task<JsonDocument> SearchAsync(
        string[] roots, string query)
    {
        return SendAsync(new
        {
            request_id = Guid.NewGuid().ToString(),
            command = "search",
            roots,
            query
        });
    }
    public Task<JsonDocument> ListModelsAsync()
    {
        return SendAsync(new
        {
            request_id = Guid.NewGuid().ToString(),
            command = "list_models"
        });
    }

    public Task<JsonDocument> AnswerAsync(
        string model,
        string query,
        JsonElement[] hits)
    {
        return SendAsync(new
        {
            request_id = Guid.NewGuid().ToString(),
            command = "answer",
            model,
            query,
            hits,
            language = "ru"
        }, 240);
    }
    private static async Task<JsonDocument> SendAsync(
        object request, int timeoutSeconds = 30)
    {
        string root = FindRepositoryRoot();

        string packagedPath = Path.Combine(
            root,
            "build", "windows-backend", "dist",
            "StudyAgentBackend", "StudyAgentBackend.exe");

        bool usePackagedBackend = File.Exists(packagedPath);

        string backendPath = usePackagedBackend
            ? packagedPath
            : Path.Combine(root, ".venv", "Scripts", "python.exe");

        var info = new ProcessStartInfo
        {
            FileName = backendPath,
            Arguments = usePackagedBackend ? "" : "-X utf8 -m study_agent.mac_bridge",
            WorkingDirectory = root,
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

        using var process = new Process
        {
            StartInfo = info
        };

        using var timeout = new CancellationTokenSource(
            TimeSpan.FromSeconds(timeoutSeconds));

        bool started = false;

        try
        {
            if (!process.Start())
            {
                throw new InvalidOperationException(
                    "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РїСѓСЃС‚РёС‚СЊ Python.");
            }

            started = true;

            Task<string> errorTask =
                process.StandardError.ReadToEndAsync(
                    timeout.Token);

            string json = JsonSerializer.Serialize(request);

            await process.StandardInput
                .WriteLineAsync(json);

            await process.StandardInput.FlushAsync();
            process.StandardInput.Close();

            string? response = await process
                .StandardOutput
                .ReadLineAsync(timeout.Token);

            await process.WaitForExitAsync(timeout.Token);

            string errors = await errorTask;

            if (process.ExitCode != 0)
            {
                throw new InvalidOperationException(
                    $"Python Р·Р°РІРµСЂС€РёР»СЃСЏ СЃ РѕС€РёР±РєРѕР№: {errors}");
            }

            if (string.IsNullOrWhiteSpace(response))
            {
                throw new InvalidOperationException(
                    $"Python РЅРµ РІРµСЂРЅСѓР» РѕС‚РІРµС‚. {errors}");
            }

            JsonDocument document =
                JsonDocument.Parse(response);

            if (!document.RootElement
                .TryGetProperty("ok", out var ok) ||
                ok.ValueKind != JsonValueKind.True)
            {
                string message = "РћС€РёР±РєР° Python-backend";

                if (document.RootElement
                    .TryGetProperty("error", out var error) &&
                    error.TryGetProperty(
                        "message", out var errorMessage))
                {
                    message =
                        errorMessage.GetString() ?? message;
                }

                document.Dispose();
                throw new InvalidOperationException(message);
            }

            return document;
        }
        catch (OperationCanceledException)
        {
            throw new TimeoutException(
                "Python-backend РЅРµ РѕС‚РІРµС‚РёР» Р·Р° 30 СЃРµРєСѓРЅРґ.");
        }
        finally
        {
            if (started && !process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
        }
    }

    private static string FindRepositoryRoot()
    {
        DirectoryInfo? directory = new DirectoryInfo(
            AppContext.BaseDirectory);

        while (directory != null)
        {
            string python = Path.Combine(
                directory.FullName,
                ".venv", "Scripts", "python.exe");

            string bridge = Path.Combine(
                directory.FullName,
                "src", "study_agent", "mac_bridge.py");

            if (File.Exists(python) && File.Exists(bridge))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException(
            "Python-backend Study Agent РЅРµ РЅР°Р№РґРµРЅ.");
    }
}



