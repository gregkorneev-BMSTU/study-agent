using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace StudyAgent_Windows.Services;

public sealed class LibraryStorageService
{
    private readonly string _filePath = Path.Combine(
        AppStorage.DataFolder,
        "library.json");

    public List<string> Load()
    {
        if (!File.Exists(_filePath))
            return new List<string>();

        string json = File.ReadAllText(_filePath);

        return JsonSerializer.Deserialize<List<string>>(json)
            ?? new List<string>();
    }

    public void Save(List<string> roots)
    {
        string directory = Path.GetDirectoryName(_filePath)!;
        Directory.CreateDirectory(directory);

        string json = JsonSerializer.Serialize(
            roots,
            new JsonSerializerOptions
            {
                WriteIndented = true
            });

        string temporaryPath = _filePath + ".tmp";

        File.WriteAllText(temporaryPath, json);

        File.Move(
            temporaryPath,
            _filePath,
            overwrite: true);
    }
}
