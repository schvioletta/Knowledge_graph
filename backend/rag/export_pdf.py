"""Экспорт RAG-ответа в PDF — вопрос, ответ, источники и уровень достоверности
в виде читаемого отчёта. Шрифт DejaVu Sans (в комплекте, `fonts/`, лицензия
Bitstream Vera — свободно распространяется) нужен для кириллицы: встроенные
шрифты fpdf2 (Helvetica и т.п.) её не поддерживают.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF

_FONT_DIR = Path(__file__).parent / "fonts"

_CONFIDENCE_COLOR = {
    "высокая": (79, 209, 197),
    "средняя": (155, 123, 255),
    "низкая": (148, 163, 184),
    "нет данных": (100, 116, 139),
}


class _ReportPDF(FPDF):
    def header(self) -> None:
        self.set_font("DejaVu", "B", 10)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "R&D Knowledge Graph — ответ по загруженным документам", align="L")
        self.ln(12)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Страница {self.page_no()}", align="C")


def _line(pdf: FPDF, h: float, text: str) -> None:
    # fpdf2's multi_cell() (в отличие от ln()) не сбрасывает x на левое поле
    # после себя — следующий вызов multi_cell/cell тогда стартует от того места,
    # где оборвалась предыдущая строка, и может упереться в правый край раньше
    # первого символа ("Not enough horizontal space..."). new_x/new_y — явный
    # сброс курсора на начало следующей строки после каждого блока текста.
    pdf.multi_cell(0, h, text, new_x="LMARGIN", new_y="NEXT")


def build_answer_pdf(
    question: str,
    answer: str,
    confidence: str,
    citations: list[dict[str, Any]],
    grounded: bool,
    llm_used: bool,
) -> bytes:
    pdf = _ReportPDF()
    pdf.add_font("DejaVu", "", str(_FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(_FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(140, 140, 140)
    _line(pdf, 6, datetime.datetime.now().strftime("Сформировано: %d.%m.%Y %H:%M"))
    pdf.ln(6)

    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(20, 20, 20)
    _line(pdf, 7, "Вопрос")
    pdf.set_font("DejaVu", "", 11)
    _line(pdf, 6, question)
    pdf.ln(4)

    pdf.set_font("DejaVu", "B", 12)
    _line(pdf, 7, "Ответ")
    r, g, b = _CONFIDENCE_COLOR.get(confidence, _CONFIDENCE_COLOR["нет данных"])
    pdf.set_font("DejaVu", "B", 9)
    pdf.set_text_color(r, g, b)
    badge = f"Достоверность: {confidence}"
    if grounded and not llm_used:
        badge += "  (без LLM-синтеза — показаны фрагменты источников)"
    _line(pdf, 6, badge)
    pdf.ln(1)
    pdf.set_font("DejaVu", "", 11)
    pdf.set_text_color(20, 20, 20)
    _line(pdf, 6, answer)
    pdf.ln(4)

    if citations:
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(20, 20, 20)
        _line(pdf, 7, "Источники")
        pdf.ln(1)
        for c in citations:
            pdf.set_font("DejaVu", "B", 10)
            pdf.set_text_color(0, 120, 190)
            _line(pdf, 6, f"[{c.get('index')}] {c.get('title', '?')} — {c.get('location', '')}")
            pdf.set_font("DejaVu", "", 9)
            pdf.set_text_color(90, 90, 90)
            snippet = (c.get("snippet") or "").strip()
            if snippet:
                _line(pdf, 5, snippet)
            pdf.ln(2)

    return bytes(pdf.output())
