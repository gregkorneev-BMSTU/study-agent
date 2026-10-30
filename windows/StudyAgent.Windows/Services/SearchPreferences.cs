using System.Globalization;

namespace StudyAgent_Windows.Services;

public static class SearchPreferences
{
    public static string DocumentPrefix
    {
        get => AppStorage.GetSetting("EmbeddingDocumentPrefix") as string ?? "";
        set => AppStorage.SetSetting("EmbeddingDocumentPrefix", value);
    }

    public static string QueryPrefix
    {
        get => AppStorage.GetSetting("EmbeddingQueryPrefix") as string ?? "";
        set => AppStorage.SetSetting("EmbeddingQueryPrefix", value);
    }

    public static double MinimumSimilarity
    {
        get => double.TryParse(AppStorage.GetSetting("MinimumSimilarity") as string,
            NumberStyles.Float, CultureInfo.InvariantCulture, out double value) && value >= 0 && value <= 1
                ? value : 0.65;
        set => AppStorage.SetSetting("MinimumSimilarity", Math.Clamp(value, 0, 1).ToString(CultureInfo.InvariantCulture));
    }

    public static PythonBridgeService.EmbeddingProfile? SelectedEmbedding()
    {
        string model = AppStorage.GetSetting("EmbeddingModel") as string ?? "";
        string dimensions = AppStorage.GetSetting("EmbeddingDimensions") as string ?? "";
        return !string.IsNullOrWhiteSpace(model) && int.TryParse(dimensions, out int count) && count > 0
            ? new PythonBridgeService.EmbeddingProfile(model, count, DocumentPrefix, QueryPrefix)
            : null;
    }
}
