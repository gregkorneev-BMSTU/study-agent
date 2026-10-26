using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace StudyAgent_Windows.Services;

public sealed class PythonBridgeService
{
    private static readonly object BackendExtractLock = new();

    private static string EnsureArchivedBackend()
    {
        string archive = Path.Combine(AppContext.BaseDirectory, "Backend.zip");
        using var stream = File.OpenRead(archive);
        string digest = Convert.ToHexString(SHA256.HashData(stream))[..16];
        // Packaged apps can virtualize Environment.SpecialFolder.LocalApplicationData.
        // Use the package's physical writable LocalState path for child processes too.
        string cacheRoot = Path.Combine(
            Windows.Storage.ApplicationData.Current.LocalFolder.Path,
            "backend-cache");
        string destination = Path.Combine(cacheRoot, digest);
        string executable = Path.Combine(destination, "StudyAgentBackend.exe");

        lock (BackendExtractLock)
        {
            if (File.Exists(executable) &&
                File.Exists(Path.Combine(destination, ".ready")))
            {
                return executable;
            }

            Directory.CreateDirectory(cacheRoot);
            string temporary = Path.Combine(cacheRoot, digest + ".extracting");
            if (Directory.Exists(temporary))
            {
                Directory.Delete(temporary, recursive: true);
            }

            ZipFile.ExtractToDirectory(archive, temporary);

            if (!File.Exists(Path.Combine(temporary, "StudyAgentBackend.exe")))
            {
                Directory.Delete(temporary, recursive: true);
                throw new FileNotFoundException(
                    "StudyAgentBackend.exe is missing from Backend.zip");
            }

            File.WriteAllText(Path.Combine(temporary, ".ready"), "ready");
            if (Directory.Exists(destination))
            {
                Directory.Delete(destination, recursive: true);
            }

            Directory.Move(temporary, destination);
            return executable;
        }
    }

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

    public Task<JsonDocument> SyncSourceAsync(string root)
    {
        return SendAsync(new
        {
            request_id = Guid.NewGuid().ToString(),
            command = "sync_source",
            root
        }, 600);
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
        string bundledPath = Path.Combine(
            AppContext.BaseDirectory,
            "Backend",
            "StudyAgentBackend.exe");

        string? root = null;
        string backendPath;

        System.Diagnostics.Debug.WriteLine(
            "StudyAgent application directory: " +
            AppContext.BaseDirectory);
        bool usePackagedBackend;

        if (File.Exists(bundledPath))
        {
            backendPath = bundledPath;
            usePackagedBackend = true;
        }
        else if (File.Exists(Path.Combine(AppContext.BaseDirectory, "Backend.zip")))
        {
            backendPath = EnsureArchivedBackend();
            usePackagedBackend = true;
        }
        else
        {
            root = FindRepositoryRoot();

            string packagedPath = Path.Combine(
                root,
                "build", "windows-backend", "dist",
                "StudyAgentBackend", "StudyAgentBackend.exe");

            usePackagedBackend = File.Exists(packagedPath);

            backendPath = usePackagedBackend
                ? packagedPath
                : Path.Combine(root, ".venv", "Scripts", "python.exe");
        }


        System.Diagnostics.Debug.WriteLine(
            "StudyAgent backend path: " + backendPath);

        var info = new ProcessStartInfo
        {
            FileName = backendPath,
            Arguments = usePackagedBackend ? "" : "-X utf8 -m study_agent.mac_bridge",
            WorkingDirectory = usePackagedBackend ? Path.GetDirectoryName(backendPath)! : root!,
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

            string? response = null;
            string? line;

            while ((line = await process.StandardOutput
                .ReadLineAsync(timeout.Token)) != null)
            {
                using var message = JsonDocument.Parse(line);

                if (message.RootElement.TryGetProperty(
                    "event", out var eventElement) &&
                    eventElement.GetString() == "progress")
                {
                    continue;
                }

                response = line;
            }

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


