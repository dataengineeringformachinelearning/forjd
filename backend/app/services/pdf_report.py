"""Render searchable, token-driven FORJD operational reports as PDF bytes.

Hand-rolled PDF renderer; uses FJORD token mirror under
``backend/static/fjord-report-tokens.json`` (no Django dependency).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import (
  timezone as datetime_timezone,
)
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast

Color = tuple[float, float, float]
TokenMap = dict[str, Any]

PDF_POINTS_PER_CSS_PIXEL: Final[float] = 0.75
PAGE_WIDTH: Final[float] = 792.0
PAGE_HEIGHT: Final[float] = 612.0
MAX_VISIBLE_ROWS: Final[int] = 1000
REGULAR_TEXT_WIDTH_FACTOR: Final[float] = 0.52
BOLD_TEXT_WIDTH_FACTOR: Final[float] = 0.60
HEADER_SINGLE_LINE_WIDTH_RATIO: Final[float] = 0.72
TITLE_COLUMN_SPAN: Final[int] = 5
TOKEN_FILE: Final[Path] = (
    Path(__file__).resolve().parents[2] / "static" / "fjord-report-tokens.json"
)
PDF_TEXT_REPLACEMENTS: Final[dict[str, str]] = {
  "\u00a0": " ",
  "\u2010": "-",
  "\u2011": "-",
  "\u2012": "-",
  "\u2013": "-",
  "\u2014": "-",
  "\u2018": "'",
  "\u2019": "'",
  "\u201c": '"',
  "\u201d": '"',
  "\u2022": "-",
  "\u2026": "...",
}


@dataclass(frozen=True)
class PdfReportTheme:
  """Resolved Viking-UI values expressed in PDF points and RGB channels."""

  brand_navy: Color
  brand_blue: Color
  page: Color
  surface: Color
  surface_alt: Color
  text: Color
  text_muted: Color
  on_header: Color
  on_header_muted: Color
  border: Color
  table_header: Color
  table_header_border: Color
  accent: Color
  margin: float
  gap: float
  compact_gap: float
  grid_unit: float
  border_width: float
  radius: float
  brand_copy_width: float
  minimum_column_width: float
  layout_columns: int
  header_height: float
  summary_height: float
  footer_height: float
  logo_size: float
  table_header_height: float
  table_row_height: float
  cell_padding: float
  font_title: float
  font_subtitle: float
  font_meta: float
  font_label: float
  font_body: float


@dataclass(frozen=True)
class PdfPageContent:
  """One PDF content stream and the semantic roles referenced by its MCIDs."""

  stream: bytes
  roles: tuple[str, ...]


def _token_value(tokens: TokenMap, path: str) -> Any:
  current: Any = tokens
  for part in path.split("."):
    if not isinstance(current, dict) or part not in current:
      raise RuntimeError(f"Missing Viking-UI report token: {path}")
    current = current[part]
  return current


def _resolve_color(tokens: TokenMap, path: str) -> Color:
  visited: set[str] = set()
  current_path = path
  while True:
    if current_path in visited:
      raise RuntimeError(f"Circular Viking-UI color token: {path}")
    visited.add(current_path)
    raw = _token_value(tokens, current_path)
    if not isinstance(raw, str):
      raise RuntimeError(f"Viking-UI color token is not a string: {current_path}")
    value = raw.strip()
    if value.startswith("#") and len(value) == 7:
      return cast(
        Color,
        tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)),
      )
    if value.startswith("{") and value.endswith("}"):
      current_path = value[1:-1]
      continue
    current_path = value if value.startswith("color.") else f"color.{value}"


def _resolve_points(tokens: TokenMap, path: str) -> float:
  raw = _token_value(tokens, path)
  if not isinstance(raw, str) or not raw.endswith("px"):
    raise RuntimeError(f"Viking-UI length token is not expressed in pixels: {path}")
  return float(raw.removesuffix("px")) * PDF_POINTS_PER_CSS_PIXEL


@lru_cache(maxsize=1)
def load_pdf_report_theme() -> PdfReportTheme:
  """Load the generated Viking token mirror used by the backend report renderer."""
  try:
    tokens = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as exc:
    raise RuntimeError(
      "The Viking-UI token mirror is unavailable; run scripts/sync_design_system.py"
    ) from exc

  font_body = _resolve_points(tokens, "typography.fontSize.xs")
  grid_unit = _resolve_points(tokens, "spacing.gridUnit")
  line_height = float(_token_value(tokens, "typography.lineHeight.normal"))
  return PdfReportTheme(
    brand_navy=_resolve_color(tokens, "color.brand.navy"),
    brand_blue=_resolve_color(tokens, "color.brand.blue"),
    page=_resolve_color(tokens, "semantic.light.bg"),
    surface=_resolve_color(tokens, "semantic.light.surface"),
    surface_alt=_resolve_color(tokens, "semantic.light.surfaceAlt"),
    text=_resolve_color(tokens, "semantic.light.text"),
    text_muted=_resolve_color(tokens, "semantic.light.textMuted"),
    on_header=_resolve_color(tokens, "color.whitePure"),
    on_header_muted=_resolve_color(tokens, "color.navy.200"),
    border=_resolve_color(tokens, "color.navy.100"),
    table_header=_resolve_color(tokens, "color.navy.800"),
    table_header_border=_resolve_color(tokens, "color.navy.500"),
    accent=_resolve_color(tokens, "semantic.light.accent"),
    margin=_resolve_points(tokens, "spacing.5"),
    gap=_resolve_points(tokens, "spacing.2"),
    compact_gap=_resolve_points(tokens, "spacing.1"),
    grid_unit=grid_unit,
    border_width=_resolve_points(tokens, "spacing.px"),
    radius=_resolve_points(tokens, "radius.lg"),
    brand_copy_width=_resolve_points(tokens, "spacing.24"),
    minimum_column_width=_resolve_points(tokens, "spacing.6"),
    layout_columns=int(_token_value(tokens, "layout.columns")),
    header_height=_resolve_points(tokens, "spacing.10"),
    summary_height=_resolve_points(tokens, "spacing.7"),
    footer_height=_resolve_points(tokens, "spacing.3"),
    logo_size=_resolve_points(tokens, "spacing.4"),
    table_header_height=_resolve_points(tokens, "spacing.5"),
    table_row_height=(font_body * line_height) + (grid_unit * 2),
    cell_padding=_resolve_points(tokens, "spacing.1"),
    font_title=_resolve_points(tokens, "typography.fontSize.xl"),
    font_subtitle=_resolve_points(tokens, "typography.fontSize.sm"),
    font_meta=_resolve_points(tokens, "typography.fontSize.sm"),
    font_label=_resolve_points(tokens, "typography.fontSize.2xs"),
    font_body=font_body,
  )


def _number(value: float) -> str:
  return f"{value:.3f}".rstrip("0").rstrip(".")


def _color_command(color: Color, *, stroke: bool = False) -> str:
  operator = "RG" if stroke else "rg"
  return f"{' '.join(_number(channel) for channel in color)} {operator}"


def _safe_text(value: Any) -> str:
  if value is None:
    return "-"
  if isinstance(value, bool):
    return "Yes" if value else "No"
  text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
  for source, replacement in PDF_TEXT_REPLACEMENTS.items():
    text = text.replace(source, replacement)
  return " ".join(text.split())


def _escape_pdf_text(value: Any) -> str:
  return _safe_text(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _estimated_text_width(text: str, font_size: float, *, bold: bool = False) -> float:
  width_factor = BOLD_TEXT_WIDTH_FACTOR if bold else REGULAR_TEXT_WIDTH_FACTOR
  return len(text) * font_size * width_factor


def _fit_text(value: Any, max_width: float, font_size: float, *, bold: bool = False) -> str:
  text = _safe_text(value)
  if _estimated_text_width(text, font_size, bold=bold) <= max_width:
    return text
  ellipsis = "..."
  available = max_width - _estimated_text_width(ellipsis, font_size, bold=bold)
  width_factor = BOLD_TEXT_WIDTH_FACTOR if bold else REGULAR_TEXT_WIDTH_FACTOR
  max_chars = max(1, int(available / (font_size * width_factor)))
  return f"{text[:max_chars].rstrip()}{ellipsis}"


def _append_text(
  commands: list[str],
  text: Any,
  *,
  x: float,
  y: float,
  font: str,
  size: float,
  color: Color,
  max_width: float | None = None,
  align: str = "left",
) -> None:
  value = _safe_text(text)
  if max_width is not None:
    value = _fit_text(value, max_width, size, bold=font == "F2")
  text_width = _estimated_text_width(value, size, bold=font == "F2")
  text_x = x
  if align == "right" and max_width is not None:
    text_x = x + max_width - text_width
  commands.extend(
    [
      "BT",
      f"/{font} {_number(size)} Tf",
      _color_command(color),
      f"1 0 0 1 {_number(text_x)} {_number(y)} Tm",
      f"({_escape_pdf_text(value)}) Tj",
      "ET",
    ]
  )


def _rounded_rect_path(x: float, y: float, width: float, height: float, radius: float) -> str:
  radius = max(0.0, min(radius, width / 2, height / 2))
  control = radius * 0.55228475
  return "\n".join(
    [
      f"{_number(x + radius)} {_number(y)} m",
      f"{_number(x + width - radius)} {_number(y)} l",
      (
        f"{_number(x + width - radius + control)} {_number(y)} "
        f"{_number(x + width)} {_number(y + radius - control)} "
        f"{_number(x + width)} {_number(y + radius)} c"
      ),
      f"{_number(x + width)} {_number(y + height - radius)} l",
      (
        f"{_number(x + width)} {_number(y + height - radius + control)} "
        f"{_number(x + width - radius + control)} {_number(y + height)} "
        f"{_number(x + width - radius)} {_number(y + height)} c"
      ),
      f"{_number(x + radius)} {_number(y + height)} l",
      (
        f"{_number(x + radius - control)} {_number(y + height)} "
        f"{_number(x)} {_number(y + height - radius + control)} "
        f"{_number(x)} {_number(y + height - radius)} c"
      ),
      f"{_number(x)} {_number(y + radius)} l",
      (
        f"{_number(x)} {_number(y + radius - control)} "
        f"{_number(x + radius - control)} {_number(y)} "
        f"{_number(x + radius)} {_number(y)} c"
      ),
      "h",
    ]
  )


def _append_rounded_rect(
  commands: list[str],
  *,
  x: float,
  y: float,
  width: float,
  height: float,
  radius: float,
  fill: Color,
  stroke: Color | None = None,
  stroke_width: float = 0,
) -> None:
  commands.extend(["q", _color_command(fill)])
  if stroke is not None:
    commands.extend([_color_command(stroke, stroke=True), f"{_number(stroke_width)} w"])
  commands.append(_rounded_rect_path(x, y, width, height, radius))
  commands.extend(["B" if stroke is not None else "f", "Q"])


def _append_brand_mark(
  commands: list[str], *, x: float, y: float, size: float, theme: PdfReportTheme
) -> None:
  scale = size / 24.0
  stroke_width = max(theme.border_width, theme.border_width * 2 * scale)

  def point(svg_x: float, svg_y: float) -> str:
    return f"{_number(x + (svg_x * scale))} {_number(y + ((24 - svg_y) * scale))}"

  commands.extend(
    [
      "q",
      _color_command(theme.brand_blue, stroke=True),
      f"{_number(stroke_width)} w",
      "1 J",
      "1 j",
    ]
  )
  # Canonical Viking-UI Drakkar outline translated from its 24 x 24 SVG geometry.
  commands.extend(
    [
      f"{point(12, 14)} m {point(12, 2)} l S",
      (
        f"{point(19, 13)} m {point(19, 7)} l "
        f"{point(19, 5.895)} {point(18.105, 5)} {point(17, 5)} c "
        f"{point(7, 5)} l "
        f"{point(5.895, 5)} {point(5, 5.895)} {point(5, 7)} c "
        f"{point(5, 13)} l S"
      ),
      (
        f"{point(3, 14)} m {point(11.188, 10.361)} l "
        f"{point(11.704, 10.132)} {point(12.296, 10.132)} {point(12.812, 10.361)} c "
        f"{point(21, 14)} l "
        f"{point(21, 16.4)} {point(20.45, 18.43)} {point(19.38, 20)} c S"
      ),
      (
        f"{point(2, 21)} m "
        f"{point(2.6, 21.5)} {point(3.2, 22)} {point(4.5, 22)} c "
        f"{point(7, 22)} {point(7, 20)} {point(9.5, 20)} c "
        f"{point(10.8, 20)} {point(11.4, 20.5)} {point(12, 21)} c "
        f"{point(12.6, 21.5)} {point(13.2, 22)} {point(14.5, 22)} c "
        f"{point(17, 22)} {point(17, 20)} {point(19.5, 20)} c "
        f"{point(20.8, 20)} {point(21.4, 20.5)} {point(22, 21)} c S"
      ),
    ]
  )
  commands.append("Q")


def _append_header_chrome(commands: list[str], *, theme: PdfReportTheme) -> None:
  header_y = PAGE_HEIGHT - theme.header_height
  commands.extend(
    [
      _color_command(theme.brand_navy),
      f"0 {_number(header_y)} {_number(PAGE_WIDTH)} {_number(theme.header_height)} re f",
      _color_command(theme.brand_blue),
      f"0 {_number(header_y)} {_number(PAGE_WIDTH)} {_number(theme.grid_unit)} re f",
    ]
  )
  logo_y = PAGE_HEIGHT - theme.compact_gap - theme.logo_size
  _append_brand_mark(commands, x=theme.margin, y=logo_y, size=theme.logo_size, theme=theme)
  lockup_x = theme.margin + theme.logo_size + theme.compact_gap
  _append_text(
    commands,
    "FORJD",
    x=lockup_x,
    y=PAGE_HEIGHT - theme.gap - theme.font_subtitle,
    font="F2",
    size=theme.font_subtitle,
    color=theme.on_header,
  )
  _append_text(
    commands,
    "DATA ENGINEERING FOR AI ENGINEERING AND CYBERSECURITY",
    x=lockup_x,
    y=PAGE_HEIGHT - theme.gap - theme.font_subtitle - theme.font_label - theme.grid_unit,
    font="F1",
    size=theme.font_label,
    color=theme.on_header_muted,
    max_width=theme.brand_copy_width,
  )


def _append_header_title(commands: list[str], *, title: str, theme: PdfReportTheme) -> None:
  available = PAGE_WIDTH - (theme.margin * 2)
  title_x = theme.margin + (available * (TITLE_COLUMN_SPAN / theme.layout_columns))
  _append_text(
    commands,
    title,
    x=title_x,
    y=PAGE_HEIGHT - (theme.header_height / 2) - (theme.font_title / 3),
    font="F2",
    size=theme.font_title,
    color=theme.on_header,
    max_width=PAGE_WIDTH - theme.margin - title_x,
  )


def _append_summary(
  commands: list[str], *, items: list[tuple[str, str]], y: float, theme: PdfReportTheme
) -> None:
  available = PAGE_WIDTH - (theme.margin * 2)
  card_gap = theme.gap
  card_width = (available - (card_gap * (len(items) - 1))) / len(items)
  for index, (label, value) in enumerate(items):
    x = theme.margin + (index * (card_width + card_gap))
    _append_rounded_rect(
      commands,
      x=x,
      y=y,
      width=card_width,
      height=theme.summary_height,
      radius=theme.radius,
      fill=theme.surface,
      stroke=theme.border,
      stroke_width=theme.border_width,
    )
    _append_text(
      commands,
      label.upper(),
      x=x + theme.compact_gap,
      y=y + theme.summary_height - theme.compact_gap - theme.font_label,
      font="F2",
      size=theme.font_label,
      color=theme.text_muted,
      max_width=card_width - (theme.compact_gap * 2),
    )
    _append_text(
      commands,
      value,
      x=x + theme.compact_gap,
      y=y + theme.compact_gap,
      font="F2",
      size=theme.font_meta,
      color=theme.text,
      max_width=card_width - (theme.compact_gap * 2),
    )


def _humanize_header(header: str) -> str:
  return header.replace("_", " ").strip().upper()


def _header_lines(header: str, *, max_width: float, font_size: float) -> list[str]:
  label = _humanize_header(header)
  label_width = _estimated_text_width(label, font_size, bold=True)
  words = label.split()
  if label_width <= max_width and (
    len(words) < 2 or label_width <= max_width * HEADER_SINGLE_LINE_WIDTH_RATIO
  ):
    return [label]

  if len(words) < 2:
    return [_fit_text(label, max_width, font_size, bold=True)]

  candidates = [
    (" ".join(words[:index]), " ".join(words[index:])) for index in range(1, len(words))
  ]
  first, second = min(
    candidates,
    key=lambda pair: max(
      _estimated_text_width(pair[0], font_size, bold=True),
      _estimated_text_width(pair[1], font_size, bold=True),
    ),
  )
  return [
    _fit_text(first, max_width, font_size, bold=True),
    _fit_text(second, max_width, font_size, bold=True),
  ]


def _column_widths(
  rows: list[dict[str, Any]], headers: list[str], *, available: float, theme: PdfReportTheme
) -> list[float]:
  if not headers:
    return []
  sampled = rows[:100]
  weights: list[float] = []
  for header in headers:
    longest = max(
      [len(_humanize_header(header)), *(len(_safe_text(row.get(header))) for row in sampled)],
      default=len(header),
    )
    weights.append(float(max(6, min(longest, 28))))
  weight_total = sum(weights) or float(len(headers))
  minimum = min(_resolve_minimum_column_width(theme), available / len(headers))
  widths = [max(minimum, available * (weight / weight_total)) for weight in weights]
  overflow = sum(widths) - available
  if overflow > 0:
    flexible = [max(0.0, width - minimum) for width in widths]
    flexible_total = sum(flexible)
    if flexible_total > 0:
      widths = [
        width - (overflow * (room / flexible_total))
        for width, room in zip(widths, flexible, strict=True)
      ]
    else:
      widths = [available / len(headers)] * len(headers)
  widths[-1] += available - sum(widths)
  return widths


def _resolve_minimum_column_width(theme: PdfReportTheme) -> float:
  return max(theme.minimum_column_width, (theme.cell_padding * 2) + (theme.font_body * 4))


def _numeric_headers(rows: list[dict[str, Any]], headers: list[str]) -> set[str]:
  numeric: set[str] = set()
  for header in headers:
    values = [row.get(header) for row in rows[:100] if row.get(header) is not None]
    if values and all(
      isinstance(value, int | float) and not isinstance(value, bool) for value in values
    ):
      numeric.add(header)
  return numeric


def _append_table(
  commands: list[str],
  *,
  rows: list[dict[str, Any]],
  headers: list[str],
  widths: list[float],
  numeric_headers: set[str],
  top: float,
  status_text: str,
  theme: PdfReportTheme,
) -> None:
  available = PAGE_WIDTH - (theme.margin * 2)
  _append_text(
    commands,
    "REPORT DATA",
    x=theme.margin,
    y=top - theme.font_label,
    font="F2",
    size=theme.font_label,
    color=theme.accent,
  )
  _append_text(
    commands,
    status_text.upper(),
    x=theme.margin,
    y=top - theme.font_label,
    font="F1",
    size=theme.font_label,
    color=theme.text_muted,
    max_width=available,
    align="right",
  )
  header_top = top - theme.footer_height
  header_y = header_top - theme.table_header_height
  commands.extend(
    [
      _color_command(theme.table_header),
      (
        f"{_number(theme.margin)} {_number(header_y)} {_number(available)} "
        f"{_number(theme.table_header_height)} re f"
      ),
    ]
  )
  x = theme.margin
  for header, width in zip(headers, widths, strict=True):
    cell_width = width - (theme.cell_padding * 2)
    lines = _header_lines(header, max_width=cell_width, font_size=theme.font_label)
    line_step = theme.font_label + (theme.grid_unit / 2)
    block_height = theme.font_label + ((len(lines) - 1) * line_step)
    bottom_baseline = header_y + ((theme.table_header_height - block_height) / 2)
    for line_index, line in enumerate(lines):
      _append_text(
        commands,
        line,
        x=x + theme.cell_padding,
        y=bottom_baseline + ((len(lines) - line_index - 1) * line_step),
        font="F2",
        size=theme.font_label,
        color=theme.on_header,
        max_width=cell_width,
      )
    x += width
    if x < theme.margin + available:
      commands.extend(
        [
          _color_command(theme.table_header_border, stroke=True),
          f"{_number(theme.border_width)} w",
          (
            f"{_number(x)} {_number(header_y)} m "
            f"{_number(x)} {_number(header_y + theme.table_header_height)} l S"
          ),
        ]
      )

  row_y = header_y
  for row_index, row in enumerate(rows):
    row_y -= theme.table_row_height
    fill = theme.surface if row_index % 2 == 0 else theme.surface_alt
    commands.extend(
      [
        _color_command(fill),
        (
          f"{_number(theme.margin)} {_number(row_y)} {_number(available)} "
          f"{_number(theme.table_row_height)} re f"
        ),
        _color_command(theme.border, stroke=True),
        f"{_number(theme.border_width)} w",
        (
          f"{_number(theme.margin)} {_number(row_y)} m "
          f"{_number(theme.margin + available)} {_number(row_y)} l S"
        ),
      ]
    )
    x = theme.margin
    for header, width in zip(headers, widths, strict=True):
      cell_width = width - (theme.cell_padding * 2)
      _append_text(
        commands,
        row.get(header),
        x=x + theme.cell_padding,
        y=row_y + ((theme.table_row_height - theme.font_body) / 2),
        font="F1",
        size=theme.font_body,
        color=theme.text,
        max_width=cell_width,
        align="right" if header in numeric_headers else "left",
      )
      x += width


def _append_empty_state(commands: list[str], *, top: float, theme: PdfReportTheme) -> None:
  available = PAGE_WIDTH - (theme.margin * 2)
  height = theme.summary_height * 2
  y = top - theme.footer_height - height
  _append_text(
    commands,
    "REPORT DATA",
    x=theme.margin,
    y=top - theme.font_label,
    font="F2",
    size=theme.font_label,
    color=theme.accent,
  )
  _append_rounded_rect(
    commands,
    x=theme.margin,
    y=y,
    width=available,
    height=height,
    radius=theme.radius,
    fill=theme.surface,
    stroke=theme.border,
    stroke_width=theme.border_width,
  )
  _append_text(
    commands,
    "No data for selected range",
    x=theme.margin + theme.gap,
    y=y + (height / 2) + theme.grid_unit,
    font="F2",
    size=theme.font_subtitle,
    color=theme.text,
    max_width=available - (theme.gap * 2),
  )
  _append_text(
    commands,
    "The report was generated successfully, but no matching records were available.",
    x=theme.margin + theme.gap,
    y=y + (height / 2) - theme.font_meta,
    font="F1",
    size=theme.font_meta,
    color=theme.text_muted,
    max_width=available - (theme.gap * 2),
  )


def _append_footer(
  commands: list[str], *, page_number: int, page_count: int, theme: PdfReportTheme
) -> None:
  footer_y = theme.margin
  available = PAGE_WIDTH - (theme.margin * 2)
  commands.extend(
    [
      _color_command(theme.border, stroke=True),
      f"{_number(theme.border_width)} w",
      (
        f"{_number(theme.margin)} {_number(footer_y + theme.footer_height)} m "
        f"{_number(theme.margin + available)} {_number(footer_y + theme.footer_height)} l S"
      ),
    ]
  )
  _append_text(
    commands,
    "FORJD / CONFIDENTIAL OPERATIONAL REPORT",
    x=theme.margin,
    y=footer_y + theme.grid_unit,
    font="F2",
    size=theme.font_label,
    color=theme.text_muted,
  )
  _append_text(
    commands,
    f"PAGE {page_number} / {page_count}",
    x=theme.margin,
    y=footer_y + theme.grid_unit,
    font="F2",
    size=theme.font_label,
    color=theme.text_muted,
    max_width=available,
    align="right",
  )


def _begin_structured_content(commands: list[str], roles: list[str], *, role: str) -> None:
  mcid = len(roles)
  commands.append(f"/{role} <</MCID {mcid}>> BDC")
  roles.append(role)


def _end_marked_content(commands: list[str]) -> None:
  commands.append("EMC")


def _page_capacity(*, table_top: float, theme: PdfReportTheme) -> int:
  table_body_top = table_top - theme.footer_height - theme.table_header_height
  table_bottom = theme.margin + theme.footer_height + theme.compact_gap
  return max(1, math.floor((table_body_top - table_bottom) / theme.table_row_height))


def _paginate_rows(
  rows: list[dict[str, Any]], *, first_capacity: int, continuation_capacity: int
) -> list[list[dict[str, Any]]]:
  if not rows:
    return [[]]
  pages = [rows[:first_capacity]]
  cursor = first_capacity
  while cursor < len(rows):
    pages.append(rows[cursor : cursor + continuation_capacity])
    cursor += continuation_capacity
  return pages


def _page_streams(
  rows: list[dict[str, Any]],
  *,
  title: str,
  metadata: dict[str, str],
  generated_at: datetime,
  theme: PdfReportTheme,
) -> list[PdfPageContent]:
  visible_rows = rows[:MAX_VISIBLE_ROWS]
  headers = list(visible_rows[0].keys()) if visible_rows else []
  available = PAGE_WIDTH - (theme.margin * 2)
  widths = _column_widths(visible_rows, headers, available=available, theme=theme)
  numeric_headers = _numeric_headers(visible_rows, headers)
  header_bottom = PAGE_HEIGHT - theme.header_height
  summary_y = header_bottom - theme.gap - theme.summary_height
  first_table_top = summary_y - theme.gap
  continuation_table_top = header_bottom - theme.gap
  first_capacity = _page_capacity(table_top=first_table_top, theme=theme)
  continuation_capacity = _page_capacity(table_top=continuation_table_top, theme=theme)
  pages = _paginate_rows(
    visible_rows,
    first_capacity=first_capacity,
    continuation_capacity=continuation_capacity,
  )
  page_count = len(pages)
  shown = len(visible_rows)
  status_text = (
    f"Showing {shown:,} of {len(rows):,} records" if shown < len(rows) else f"{len(rows):,} records"
  )
  generated_label = generated_at.astimezone(datetime_timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
  summary_items = [
    ("Records", f"{len(rows):,}"),
    ("Reporting window", metadata.get("Reporting window", "Selected range")),
    ("Scope", metadata.get("Scope", "All monitored sites")),
    ("Generated", generated_label),
  ]

  page_contents: list[PdfPageContent] = []
  for page_index, page_rows in enumerate(pages):
    roles: list[str] = []
    commands = [
      "/Artifact BMC",
      "q",
      _color_command(theme.page),
      f"0 0 {_number(PAGE_WIDTH)} {_number(PAGE_HEIGHT)} re f",
      "Q",
    ]
    _append_header_chrome(commands, theme=theme)
    _end_marked_content(commands)
    if page_index == 0:
      _begin_structured_content(commands, roles, role="H1")
      _append_header_title(commands, title=title, theme=theme)
      _end_marked_content(commands)
    else:
      commands.append("/Artifact BMC")
      _append_header_title(commands, title=title, theme=theme)
      _end_marked_content(commands)
    if page_index == 0:
      _begin_structured_content(commands, roles, role="Sect")
      _append_summary(commands, items=summary_items, y=summary_y, theme=theme)
      _end_marked_content(commands)
      table_top = first_table_top
    else:
      table_top = continuation_table_top
    if headers:
      _begin_structured_content(commands, roles, role="Table")
      _append_table(
        commands,
        rows=page_rows,
        headers=headers,
        widths=widths,
        numeric_headers=numeric_headers,
        top=table_top,
        status_text=status_text,
        theme=theme,
      )
      _end_marked_content(commands)
    else:
      _begin_structured_content(commands, roles, role="Sect")
      _append_empty_state(commands, top=table_top, theme=theme)
      _end_marked_content(commands)
    commands.append("/Artifact BMC")
    _append_footer(
      commands,
      page_number=page_index + 1,
      page_count=page_count,
      theme=theme,
    )
    _end_marked_content(commands)
    page_contents.append(
      PdfPageContent(
        stream="\n".join(commands).encode("cp1252", errors="replace"),
        roles=tuple(roles),
      )
    )
  return page_contents


def render_pdf_report(
  rows: list[dict[str, Any]],
  *,
  title: str,
  metadata: dict[str, str] | None = None,
) -> bytes:
  """Create a landscape FORJD report with branded header, summary, table, and footer."""
  theme = load_pdf_report_theme()
  generated_at = datetime.now(UTC)
  page_contents = _page_streams(
    rows,
    title=title,
    metadata=metadata or {},
    generated_at=generated_at,
    theme=theme,
  )
  page_ids = [3 + (index * 2) for index in range(len(page_contents))]
  content_ids = [page_id + 1 for page_id in page_ids]
  regular_font_id = 3 + (len(page_contents) * 2)
  bold_font_id = regular_font_id + 1
  info_id = bold_font_id + 1
  structure_root_id = info_id + 1
  parent_tree_id = structure_root_id + 1
  document_structure_id = parent_tree_id + 1
  next_structure_id = document_structure_id + 1
  structure_ids_by_page: list[list[int]] = []
  for page_content in page_contents:
    structure_ids = list(range(next_structure_id, next_structure_id + len(page_content.roles)))
    structure_ids_by_page.append(structure_ids)
    next_structure_id += len(structure_ids)
  kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
  objects: list[bytes] = [
    (
      f"1 0 obj<< /Type /Catalog /Pages 2 0 R /Lang (en-US) "
      f"/StructTreeRoot {structure_root_id} 0 R /MarkInfo << /Marked true >> "
      "/ViewerPreferences << /DisplayDocTitle true >> >>endobj\n"
    ).encode(),
    (f"2 0 obj<< /Type /Pages /Kids [{kids}] /Count {len(page_contents)} >>endobj\n").encode(),
  ]
  for page_index, (page_id, content_id, page_content) in enumerate(
    zip(page_ids, content_ids, page_contents, strict=True)
  ):
    objects.append(
      (
        f"{page_id} 0 obj<< /Type /Page /Parent 2 0 R "
        f"/StructParents {page_index} "
        f"/MediaBox [0 0 {_number(PAGE_WIDTH)} {_number(PAGE_HEIGHT)}] "
        f"/Contents {content_id} 0 R /Resources << /Font << "
        f"/F1 {regular_font_id} 0 R /F2 {bold_font_id} 0 R >> >> >>endobj\n"
      ).encode()
    )
    objects.append(
      f"{content_id} 0 obj<< /Length {len(page_content.stream)} >>stream\n".encode()
      + page_content.stream
      + b"\nendstream\nendobj\n"
    )
  objects.extend(
    [
      (
        f"{regular_font_id} 0 obj<< /Type /Font /Subtype /Type1 "
        "/BaseFont /Helvetica /Encoding /WinAnsiEncoding >>endobj\n"
      ).encode(),
      (
        f"{bold_font_id} 0 obj<< /Type /Font /Subtype /Type1 "
        "/BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>endobj\n"
      ).encode(),
      (
        f"{info_id} 0 obj<< /Title ({_escape_pdf_text(title)}) "
        "/Author (Data Engineering for AI Engineering and Cybersecurity) "
        "/Subject (FORJD operational data export) /Creator (FORJD Platform) "
        f"/CreationDate (D:{generated_at.astimezone(datetime_timezone.utc).strftime('%Y%m%d%H%M%SZ')}) "
        ">>endobj\n"
      ).encode("cp1252", errors="replace"),
    ]
  )
  all_structure_ids = [
    structure_id
    for page_ids_for_structure in structure_ids_by_page
    for structure_id in page_ids_for_structure
  ]
  document_kids = " ".join(f"{structure_id} 0 R" for structure_id in all_structure_ids)
  parent_entries = " ".join(
    f"{page_index} [{' '.join(f'{structure_id} 0 R' for structure_id in structure_ids)}]"
    for page_index, structure_ids in enumerate(structure_ids_by_page)
  )
  objects.extend(
    [
      (
        f"{structure_root_id} 0 obj<< /Type /StructTreeRoot "
        f"/K {document_structure_id} 0 R /ParentTree {parent_tree_id} 0 R "
        f"/ParentTreeNextKey {len(page_contents)} >>endobj\n"
      ).encode(),
      (f"{parent_tree_id} 0 obj<< /Nums [{parent_entries}] >>endobj\n").encode(),
      (
        f"{document_structure_id} 0 obj<< /Type /StructElem /S /Document "
        f"/P {structure_root_id} 0 R /K [{document_kids}] >>endobj\n"
      ).encode(),
    ]
  )
  for page_index, (page_content, structure_ids) in enumerate(
    zip(page_contents, structure_ids_by_page, strict=True)
  ):
    for mcid, (role, structure_id) in enumerate(
      zip(page_content.roles, structure_ids, strict=True)
    ):
      objects.append(
        (
          f"{structure_id} 0 obj<< /Type /StructElem /S /{role} "
          f"/P {document_structure_id} 0 R /Pg {page_ids[page_index]} 0 R "
          f"/K {mcid} >>endobj\n"
        ).encode()
      )

  output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
  offsets = [0]
  for obj in objects:
    offsets.append(len(output))
    output.extend(obj)
  xref_position = len(output)
  output.extend(f"xref\n0 {len(offsets)}\n".encode())
  output.extend(b"0000000000 65535 f \n")
  for offset in offsets[1:]:
    output.extend(f"{offset:010d} 00000 n \n".encode())
  output.extend(
    (
      f"trailer<< /Size {len(offsets)} /Root 1 0 R /Info {info_id} 0 R >>\n"
      f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()
  )
  return bytes(output)
