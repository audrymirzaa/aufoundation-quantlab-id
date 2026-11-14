from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GridColumn:
    field: str
    label: str
    kind: str = "number"
    source: str = ""
    transform: str = "identity"
    decimals: int = 2
    visible: bool = True
    width: int | None = None


DEFAULT_COLUMNS: list[GridColumn] = [
    GridColumn(field="date", label="Tanggal", kind="date", source="date", transform="identity", decimals=0),
    GridColumn(field="close", label="Close", kind="number", source="price", transform="identity", decimals=2),
    GridColumn(field="return", label="Return %", kind="percent", source="price", transform="price_to_return", decimals=2),
    GridColumn(field="open", label="Open", kind="number", source="open", transform="identity", decimals=2),
    GridColumn(field="high", label="High", kind="number", source="high", transform="identity", decimals=2),
    GridColumn(field="low", label="Low", kind="number", source="low", transform="identity", decimals=2),
    GridColumn(field="volume", label="Volume", kind="volume", source="volume", transform="identity", decimals=0),
]

DERIVED_COLUMNS: list[GridColumn] = [
    GridColumn(field="return", label="Return %", kind="percent", source="price", transform="price_to_return"),
    GridColumn(field="change", label="Change %", kind="percent", source="change", transform="percent_to_decimal"),
]


@dataclass
class GridState:
    columns: list[GridColumn] = field(default_factory=lambda: list(DEFAULT_COLUMNS))
    order: list[str] = field(default_factory=lambda: [column.field for column in DEFAULT_COLUMNS])

    def visible_columns(self) -> list[GridColumn]:
        by_field = {column.field: column for column in self.columns}
        return [by_field[field] for field in self.order if field in by_field and by_field[field].visible]

    def toggle(self, field: str, visible: bool) -> None:
        for column in self.columns:
            if column.field == field:
                column.visible = visible
                return
        raise KeyError(f"Kolom {field!r} tidak ada.")


def column_catalog() -> list[dict[str, object]]:
    catalog: list[dict[str, object]] = []
    for column in DEFAULT_COLUMNS:
        catalog.append(
            {
                "field": column.field,
                "label": column.label,
                "kind": column.kind,
                "source": column.source,
                "transform": column.transform,
            }
        )
    return catalog
