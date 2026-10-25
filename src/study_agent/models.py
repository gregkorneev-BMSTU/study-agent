"""Shared data structures and core domain models."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedBlock:
    """Define contract to SA-01, SA-02, SA-03"""

    text: str  # clean text without ## Page
    source_type: str
    extraction_type: str

    page_number: int | None = None
    heading: str | None = None
    marker: str | None = None

    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize data to dict for json cache."""
        return {
            "text": self.text,
            "source_type": self.source_type,
            "extraction_type": self.extraction_type,
            "page_number": self.page_number,
            "heading": self.heading,
            "marker": self.marker,
            "warnings": self.warnings,
        }
