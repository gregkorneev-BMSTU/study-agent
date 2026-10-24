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
    public async Task<JsonDocument> DiagnoseAsync()
    {
        string root = FindRepositoryRoot();

        string pythonPath = Path.Combine(
            root, ".venv", "Scripts", "python.exe");

        var info = new ProcessStartInfo
        {
            FileName = pythonPath,
            Arguments = "-m study_agent.mac_bridge",
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

        using var process = new Process { StartInfo = info };
        using var timeout = new CancellationTokenSource(
            TimeSpan.FromSeconds(30));

        bool started = false;

        try
        {
            if (!process.Start())
                throw new InvalidOperationException(
                    "Не удалось запустить Python.");

            started = true;

            Task<string> errorTask =
                process.StandardError.ReadToEndAsync(timeout.Token);

            string request = JsonSerializer.Serialize(new
            {
                request_id = 1,
                command = "diagnose_backend"
            });

            await process.StandardInput.WriteLineAsync(request);
            await process.StandardInput.FlushAsync();
            process.StandardInput.Close();

            string? response = await process.StandardOutput
                .ReadLineAsync(timeout.Token);

            await process.WaitForExitAsync(timeout.Token);
            string errors = await errorTask;

            if (string.IsNullOrWhiteSpace(response))
                throw new InvalidOperationException(
                    $"Python не вернул ответ. {errors}");

            var document = JsonDocument.Parse(response);

            if (!document.RootElement
                .TryGetProperty("ok", out var ok) ||
                !ok.GetBoolean())
            {
                string message = document.RootElement
                    .GetProperty("error")
                    .GetProperty("message")
                    .GetString() ?? "Неизвестная ошибка";

                document.Dispose();
                throw new InvalidOperationException(message);
            }

            return document;
        }
        catch (OperationCanceledException)
        {
            throw new TimeoutException(
                "Python не ответил за 30 секунд.");
        }
        finally
        {
            if (started && !process.HasExited)
                process.Kill(entireProcessTree: true);
        }
    }

    private static string FindRepositoryRoot()
    {
        DirectoryInfo? directory =
            new DirectoryInfo(AppContext.BaseDirectory);

        while (directory != null)
        {
            string pythonPath = Path.Combine(
                directory.FullName,
                ".venv", "Scripts", "python.exe");

            string bridgePath = Path.Combine(
                directory.FullName,
                "src", "study_agent", "mac_bridge.py");

            if (File.Exists(pythonPath) &&
                File.Exists(bridgePath))
                return directory.FullName;

            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException(
            "Не найден Python-backend Study Agent.");
    }
}
