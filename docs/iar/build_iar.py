# ruff: noqa: E501, S603
#!/usr/bin/env python3
"""Сборка комплекта ИАР: PDF, HTML-презентация и ZIP (без видеовизитки)."""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import markdown
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt
from weasyprint import HTML

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "iar"
OUT = ROOT / "artifacts" / "iar"
BUILD = OUT / "_build"
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or "google-chrome"
SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")

NAVY = RGBColor(0x16, 0x32, 0x4F)
GREEN = RGBColor(0x0F, 0x9D, 0x58)
LIGHT = RGBColor(0xF4, 0xF7, 0xF9)
GRAY = RGBColor(0x5A, 0x6B, 0x7B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x1F, 0x2A, 0x36)
ORANGE = RGBColor(0xE6, 0x7E, 0x22)

CSS = r"""
@page {
  size: A4; margin: 20mm 16mm 20mm 20mm;
  @top-right { content: "ИАР · ai_scrivener"; font-family: "Liberation Sans", Arial, sans-serif; font-size: 8pt; color: #7a8794; }
  @bottom-center { content: counter(page); font-family: "Liberation Sans", Arial, sans-serif; font-size: 9pt; color: #445566; }
}
@page:first { @top-right { content: none; } @bottom-center { content: none; } }
@page cover { @top-right { content: none; } @bottom-center { content: none; } }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Liberation Serif", "Times New Roman", Georgia, serif;
  font-size: 12.5pt; line-height: 1.5; color: #1f2a36; text-align: justify;
}
h1, h2, h3, h4 { font-family: "Liberation Sans", Arial, sans-serif; color: #16324f; text-align: left; }
h1 { font-size: 19pt; margin: 0 0 12pt 0; break-before: page; }
h2 { font-size: 15pt; margin: 18pt 0 8pt; }
h3 { font-size: 12pt; margin: 12pt 0 4pt; }
p { margin: 0 0 6pt; }
ul, ol { margin: 4pt 0 8pt 18pt; padding: 0; }
li { margin-bottom: 3pt; }
table { width: 100%; border-collapse: collapse; margin: 8pt 0 12pt; font-size: 10pt; text-align: left; }
th, td { border: 1px solid #b8c4cf; padding: 4pt 5pt; vertical-align: top; }
th { background: #e8eef4; font-family: "Liberation Sans", Arial, sans-serif; }
tr { page-break-inside: avoid; }
table { break-inside: avoid; }
figure { margin: 10pt 0 14pt; page-break-inside: avoid; text-align: center; }
figure img { max-width: 100%; height: auto; border: 1px solid #d5dde5; }
figcaption { font-family: "Liberation Sans", Arial, sans-serif; font-size: 9pt; color: #445566; margin-top: 4pt; text-align: center; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9.5pt; background: #f1f4f7; padding: 1px 3px; }
.pagebreak { page-break-after: always; }
.toc { font-size: 10pt; line-height: 1.3; break-before: page; }
.toc ul { list-style: none; margin: 0; padding-left: 0; }
.toc ul ul { padding-left: 16pt; }
.toc li { margin: 0.5pt 0; }
.toc a { color: #1f2a36; text-decoration: none; }
.toc a::after { content: " — " target-counter(attr(href), page); color: #5a6b7b; }
.cover { text-align: center; page: cover; break-after: page; }
.cover-org { font-family: "Liberation Sans", Arial, sans-serif; font-size: 10.5pt; line-height: 1.35; margin-top: 10mm; }
.cover-program { font-family: "Liberation Sans", Arial, sans-serif; font-size: 11pt; line-height: 1.4; margin-top: 22mm; }
.cover-title { font-family: "Liberation Sans", Arial, sans-serif; font-size: 20pt; font-weight: bold; margin-top: 30mm; letter-spacing: 1px; }
.cover-topic { font-family: "Liberation Sans", Arial, sans-serif; font-size: 15pt; font-weight: bold; line-height: 1.4; margin: 14mm 8mm 0; }
.cover-fields { width: 75%; margin: 26mm auto 0; border: none; font-size: 11pt; }
.cover-fields td { border: none; padding: 5pt 4pt; text-align: left; }
.cover-place { font-family: "Liberation Sans", Arial, sans-serif; font-size: 11pt; margin-top: 26mm; }
.passport { font-size: 10.8pt; line-height: 1.3; }
.passport th, .passport td { padding: 3pt 4pt; }
.passport h2 { margin-top: 10pt; }
.passport h1 { text-align: center; font-size: 16pt; }
.passport table { font-size: 9.5pt; }
.analyst table { break-inside: auto; font-size: 9pt; }
.analyst th, .analyst td { padding: 3pt 4pt; }
.doc { border: 1px solid #b8c4cf; padding: 14pt 16pt; margin: 8pt 0 16pt; background: #fbfcfd; }
.doc p, .doc li { text-align: left; }
"""


def md_to_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "md_in_html", "toc"],
        extension_configs={"toc": {"toc_depth": "2"}},
    )
    base = (DOCS / "").as_uri() + "/"
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<base href="{base}"><style>{CSS}</style></head><body>{body}</body></html>"""


def html_to_pdf(src_md: Path, dst_pdf: Path) -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    html_path = BUILD / (src_md.stem + ".html")
    html_path.write_text(md_to_html(src_md), encoding="utf-8")
    HTML(string=html_path.read_text(encoding="utf-8"), base_url=str(DOCS) + "/").write_pdf(
        str(dst_pdf)
    )
    print(f"PDF  {dst_pdf.name:45s} {dst_pdf.stat().st_size / 1024:8.1f} KB")


def add_slide(prs: Presentation, title: str, kicker: str | None = None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    # top bar
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.12))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, Inches(0.12), Inches(1.15), Inches(0.05)
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = GREEN
    accent.line.fill.background()
    if kicker:
        tb = slide.shapes.add_textbox(Inches(0.65), Inches(0.32), Inches(11.5), Inches(0.3))
        tb.text_frame.word_wrap = True
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run()
        r.text = kicker.upper()
        r.font.size = Pt(11)
        r.font.bold = True
        r.font.color.rgb = GREEN
        r.font.name = "Arial"
    tb = slide.shapes.add_textbox(Inches(0.65), Inches(0.58), Inches(12.0), Inches(0.8))
    tb.text_frame.word_wrap = True
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    r = p.add_run()
    r.text = title
    r.font.size = Pt(28)
    r.font.bold = True
    r.font.color.rgb = NAVY
    r.font.name = "Arial"
    return slide


def add_footer(slide, number: int) -> None:
    tb = slide.shapes.add_textbox(Inches(0.65), Inches(7.08), Inches(9.0), Inches(0.25))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "ИАР · Системный аналитик · 2026"
    r.font.size = Pt(9)
    r.font.color.rgb = GRAY
    r.font.name = "Arial"
    tb = slide.shapes.add_textbox(Inches(12.1), Inches(7.08), Inches(0.8), Inches(0.25))
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    r.text = str(number)
    r.font.size = Pt(10)
    r.font.bold = True
    r.font.color.rgb = NAVY
    r.font.name = "Arial"


def bullets(slide, items, left=0.8, top=1.55, width=11.8, height=5.0, size=17, color=DARK):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        if isinstance(item, tuple):
            text, level = item
        else:
            text, level = item, 0
        p.level = level
        r = p.add_run()
        r.text = ("• " if level == 0 else "– ") + text
        r.font.size = Pt(size if level == 0 else size - 2)
        r.font.color.rgb = color
        r.font.name = "Arial"
    return tb


def textbox(
    slide,
    text,
    left,
    top,
    width,
    height,
    size=16,
    bold=False,
    color=DARK,
    fill=None,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
):
    shp = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    if fill is not None:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
        shp.line.fill.background()
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    r.font.name = "Arial"
    return shp


def image_fit(slide, path, left, top, width, height):
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(width / iw, height / ih)
    w, h = iw * scale, ih * scale
    slide.shapes.add_picture(
        str(path),
        Inches(left + (width - w) / 2),
        Inches(top + (height - h) / 2),
        Inches(w),
        Inches(h),
    )


def table(slide, rows, left, top, width, height, font=12, header=True):
    shape = slide.shapes.add_table(
        len(rows), len(rows[0]), Inches(left), Inches(top), Inches(width), Inches(height)
    )
    tbl = shape.table
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = str(value)
            cell.margin_left = Inches(0.05)
            cell.margin_right = Inches(0.05)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT
                for run in p.runs:
                    run.font.size = Pt(font)
                    run.font.name = "Arial"
                    run.font.bold = header and r == 0
                    run.font.color.rgb = WHITE if header and r == 0 else DARK
            if header and r == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = NAVY
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if r % 2 else LIGHT
    return tbl


def notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def build_pptx() -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    assets = DOCS / "assets"

    # 1 title
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = NAVY
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(5.15), prs.slide_width, Inches(2.35))
    band.fill.solid()
    band.fill.fore_color.rgb = RGBColor(0x11, 0x27, 0x3D)
    band.line.fill.background()
    textbox(s, "ИТОГОВАЯ АТТЕСТАЦИОННАЯ РАБОТА", 0.8, 0.7, 11.8, 0.4, 14, True, GREEN)
    textbox(
        s,
        "Автоматизированный анализ\nнеструктурированных документов",
        0.8,
        1.3,
        11.8,
        1.5,
        34,
        True,
        WHITE,
    )
    textbox(
        s,
        "Гибридный RAG + агентная оркестрация с контролем действий\nна примере 1С:Документооборот",
        0.8,
        3.05,
        11.8,
        1.2,
        20,
        False,
        RGBColor(0xD7, 0xE2, 0xEC),
    )
    textbox(
        s,
        "Программа профессиональной переподготовки «Системный аналитик» · ФГБОУ ДПО ИРПО",
        0.8,
        4.25,
        11.8,
        0.4,
        13,
        False,
        RGBColor(0x9F, 0xB6, 0xC9),
    )
    textbox(
        s,
        "Слушатель: ____________________     Группа: __________",
        0.8,
        5.55,
        11.8,
        0.4,
        14,
        False,
        WHITE,
    )
    textbox(
        s,
        "Руководитель ИАР: ____________________     2026",
        0.8,
        6.05,
        11.8,
        0.4,
        14,
        False,
        RGBColor(0xB9, 0xC9, 0xD6),
    )
    notes(
        s,
        "0:00–0:20. Представление: тема, роль системного аналитика, демонстрационный контур 1С:ДО.",
    )

    # 2 problem
    s = add_slide(prs, "Проблема: документы есть, смысла — нет", "Актуальность")
    bullets(
        s,
        [
            "Поиск прецедентов вручную: папки, регистры, почта, память сотрудников",
            "Подготовка черновика зависит от опыта и занимает часы",
            "Знания о типовых формулировках не формализованы",
            "ИИ без контроля: риск неверного действия и отсутствие аудита",
            "Встроенные функции 1С: OCR и транскрибация, но не RAG по корпусу",
        ],
        size=19,
    )
    textbox(
        s,
        "Нужен не «чат», а проверяемый контур: источник → проект → одобрение → след",
        0.8,
        5.9,
        11.8,
        0.7,
        18,
        True,
        NAVY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    add_footer(s, len(prs.slides))
    notes(
        s,
        "0:20–1:20. Показать боль: время, качество, риски. Подвести к требованию контролируемости.",
    )

    # 3 goal/tasks
    s = add_slide(prs, "Цель и задачи", "Цели и задачи ИАР")
    textbox(
        s,
        "Разработать ПО для анализа документов и подготовки проектов решений с контролем действий ИИ",
        0.8,
        1.45,
        11.8,
        1.0,
        18,
        True,
        NAVY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    bullets(
        s,
        [
            "Проанализировать процессы и стейкхолдеров",
            "Сформулировать 74 FR и 36 NFR, построить трассируемость",
            "Обосновать гибридный RAG и агентный цикл",
            "Спроектировать архитектуру и модель данных",
            "Реализовать прототип в 1С и внешние сервисы",
            "Оценить качество и интерпретировать результаты",
            "Определить целевую модель и границы MVP",
            "Определить границы, риски и развитие",
        ],
        top=2.8,
        width=11.6,
        size=17,
    )
    add_footer(s, len(prs.slides))
    notes(s, "1:20–2:20. Цель одной фразой, задачи — как проверяемые результаты.")

    # MVP и целевая система
    s = add_slide(prs, "MVP — фундамент целевой системы", "Замысел")
    textbox(
        s,
        "Сегодня: MVP",
        0.8,
        1.45,
        5.7,
        0.55,
        22,
        True,
        WHITE,
        fill=NAVY,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    textbox(
        s,
        "• RAG с цитатами и ссылками\n• Черновики по документу/задаче\n• Роль-промпт — на должностных обязанностях\n• Человек одобряет или возвращает\n• Автоодобрение временно; корпус — основа шаблонов",
        0.8,
        2.0,
        5.7,
        3.1,
        13.5,
        False,
        DARK,
        fill=LIGHT,
        align=PP_ALIGN.LEFT,
    )
    textbox(
        s,
        "Цель: управляемая подготовка",
        6.8,
        1.45,
        5.7,
        0.55,
        22,
        True,
        WHITE,
        fill=GREEN,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    textbox(
        s,
        "• Шаблоны: плейсхолдеры + промпты и фильтры\n• Триггер по должностным обязанностям\n• Запрос данных у другого ДЛ\n• Сбор исходных данных для расчётов\n• Решение человека; автоодобрения нет",
        6.8,
        2.0,
        5.7,
        3.1,
        13.5,
        False,
        DARK,
        fill=LIGHT,
        align=PP_ALIGN.LEFT,
    )
    textbox(
        s,
        "Текущая работа — не финал, а проверка RAG и накопление корпуса для целевой модели.",
        0.8,
        5.55,
        11.8,
        0.8,
        15,
        False,
        GRAY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    add_footer(s, len(prs.slides))
    notes(
        s,
        "Ключевая рамка: показываем MVP, но не выдаём его за финальную систему. Цель — шаблоны с поиском и фильтрами.",
    )

    # 4 stakeholders/requirements
    s = add_slide(prs, "Стейкхолдеры и требования", "Этапы · анализ")
    rows = [
        ["Стейкхолдер", "Ключевой интерес"],
        ["Должностное лицо", "Быстрый проект и проверяемый источник"],
        ["Вышестоящее ДЛ", "Контроль решений и сроков"],
        ["Администратор", "Настройки, монитор, права"],
        ["Аудитор", "Неизменяемая история и фильтры"],
        ["ИТ-служба", "Частный контур, поддержка"],
        ["Методолог / HR", "Шаблоны и регламенты"],
    ]
    table(s, rows, 0.8, 1.5, 6.5, 4.2, font=13)
    textbox(
        s,
        "70",
        7.7,
        1.6,
        2.2,
        0.9,
        44,
        True,
        GREEN,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    textbox(
        s, "функциональных требований", 7.7, 2.55, 2.2, 0.5, 12, False, GRAY, align=PP_ALIGN.CENTER
    )
    textbox(
        s,
        "36",
        10.2,
        1.6,
        2.2,
        0.9,
        44,
        True,
        NAVY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    textbox(
        s,
        "нефункциональных требований",
        10.2,
        2.55,
        2.2,
        0.5,
        12,
        False,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    textbox(
        s,
        "Матрица трассируемости: требование → дизайн → реализация → тест.\nСтатус planned = post-MVP, а не «сделано».",
        7.6,
        3.5,
        4.9,
        1.4,
        14,
        False,
        DARK,
        fill=LIGHT,
    )
    add_footer(s, len(prs.slides))
    notes(s, "2:20–3:20. Показать дисциплину требований и честные статусы.")

    # 5 AS-IS/TO-BE
    s = add_slide(prs, "От ручного поиска — к управляемому циклу", "Этапы · процессы")
    textbox(s, "AS-IS", 0.8, 1.5, 3.2, 0.4, 16, True, ORANGE)
    bullets(
        s,
        ["Ручной поиск", "Перенос фрагментов", "Нет единого аудита", "Риск ошибки"],
        0.8,
        1.95,
        3.2,
        2.8,
        15,
    )
    textbox(s, "TO-BE", 4.4, 1.5, 3.2, 0.4, 16, True, GREEN)
    bullets(
        s,
        [
            "Гибридный поиск + цитаты",
            "Черновик и инструменты",
            "Approval изменяющих действий",
            "История и атрибуция",
        ],
        4.4,
        1.95,
        3.4,
        2.8,
        15,
    )
    textbox(
        s,
        "Ключевой сдвиг: контроль переходит из памяти сотрудника в проверяемый процесс",
        0.8,
        5.55,
        11.8,
        0.75,
        17,
        True,
        NAVY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    add_footer(s, len(prs.slides))
    notes(s, "3:20–4:20. Слева боль, справа целевой процесс; справа диаграмма TO-BE.")

    # 6 architecture
    s = add_slide(prs, "Архитектура: контроль остаётся в 1С", "Этапы · проектирование")
    image_fit(s, assets / "slide_architecture_crop.png", 0.5, 1.3, 12.3, 5.2)
    textbox(
        s,
        "Расширение хранит состояние, права и аудит; сервисы stateless и не имеют доступа к базе 1С.",
        0.8,
        6.55,
        11.8,
        0.45,
        12,
        False,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    add_footer(s, len(prs.slides))
    notes(
        s, "4:20–5:20. Ключевая мысль: LLM не получает права менять данные; действия выполняет 1С."
    )

    # 7 algorithm
    s = add_slide(prs, "Алгоритм: RAG + approval-gate", "Результат · алгоритм")
    image_fit(s, assets / "slide_algorithm_crop.png", 0.55, 1.25, 12.2, 5.55)
    add_footer(s, len(prs.slides))
    notes(s, "5:20–6:20. Объяснить цикл: retrieval → step → tool → approval → audit.")

    # Целевой шаблон
    s = add_slide(prs, "Целевой шаблон: поиск вместо жёстких связей", "Целевая система")
    cards = [
        ("01 Структура", "Шаблон задаёт разделы и смысл документа."),
        ("02 Плейсхолдеры", "Что именно нужно найти для каждого поля."),
        ("03 Поиск с фильтрами", "Тип, период, автор, доступ, связи."),
        ("04 Проверка", "Источники, цитаты и решение человека."),
    ]
    for i, (h, t) in enumerate(cards):
        left = 0.55 + i * 3.08
        textbox(
            s,
            h,
            left,
            1.5,
            2.9,
            0.6,
            16,
            True,
            WHITE,
            fill=NAVY if i % 2 == 0 else GREEN,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        textbox(
            s,
            t,
            left,
            2.1,
            2.9,
            1.5,
            14,
            False,
            DARK,
            fill=LIGHT,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    textbox(
        s,
        "Фильтры заменяют жёсткие связи: шаблон не ломается при изменении структуры документа.",
        0.8,
        4.35,
        11.8,
        0.9,
        16,
        True,
        NAVY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    textbox(
        s,
        "Нужны зрелый RAG (в перспективе — агентский) и большой корпус документов.",
        0.8,
        5.5,
        11.8,
        0.6,
        14,
        False,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    add_footer(s, len(prs.slides))
    notes(
        s,
        "Целевая концепция: шаблон задаёт, что искать и по каким ограничениям, а не где лежит значение.",
    )

    # 8 demo
    s = add_slide(prs, "Как это выглядит в 1С", "Результат · демонстрация")
    image_fit(s, assets / "ui_approval_panels.png", 0.45, 1.5, 7.5, 3.45)
    textbox(
        s,
        "Запрос с замечанием и кнопкой отклонения",
        0.45,
        5.0,
        7.5,
        0.35,
        11,
        False,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    bullets(
        s,
        [
            "Что сделано и что планируется",
            "Документы с полным текстом",
            "Одобрение или отклонение с комментарием",
            "История: пользователь, инструмент, результат",
        ],
        left=8.2,
        top=1.7,
        width=4.7,
        height=3.8,
        size=15,
    )
    textbox(
        s,
        "Комментарий при одобрении не пересылается; для указаний — отклонение. История отвечает: кто, что, когда, с каким результатом.",
        0.8,
        5.55,
        11.8,
        0.9,
        14,
        False,
        DARK,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    add_footer(s, len(prs.slides))
    notes(s, "6:20–7:40. Демонстрация: замечание → отклонение → повторное одобрение → история.")

    # 9 results
    s = add_slide(prs, "Оценка: 70 кейсов", "Результат · метрики")
    chart_data = CategoryChartData()
    chart_data.categories = [
        "Correctness",
        "Groundedness",
        "Citation P",
        "Citation R",
        "No-answer P",
    ]
    chart_data.add_series("Метрика", (0.9417, 0.9536, 0.8804, 0.8833, 0.9091))
    chart = s.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.8),
        Inches(1.5),
        Inches(7.6),
        Inches(4.9),
        chart_data,
    ).chart
    chart.has_legend = False
    chart.has_title = False
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.number_format = "0.00"
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.font.size = Pt(12)
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    chart.value_axis.maximum_scale = 1.0
    chart.value_axis.minimum_scale = 0.0
    chart.value_axis.has_major_gridlines = True
    chart.value_axis.tick_labels.font.size = Pt(11)
    chart.category_axis.tick_labels.font.size = Pt(11)
    series = plot.series[0]
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = GREEN
    textbox(
        s,
        "Recall@10 = 1,00\nMRR@10 = 1,00\nnDCG@10 = 1,00",
        8.7,
        1.55,
        3.9,
        1.3,
        16,
        True,
        NAVY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    textbox(
        s,
        "E2E p50 3,18 с\nE2E p95 6,22 с\n0 галлюцинаций (судья)",
        8.7,
        3.0,
        3.9,
        1.3,
        16,
        True,
        NAVY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    textbox(
        s,
        "60 отвечаемых + 10 без ответа · top-k 10 · модель и судья GigaChat-3-Pro",
        8.7,
        4.5,
        3.9,
        0.9,
        11,
        False,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    add_footer(s, len(prs.slides))
    notes(s, "7:40–8:30. Метрики и ограничения: курируемый набор, судья на той же модели.")

    # 10 interpretation
    s = add_slide(prs, "Что означают цифры", "Результат · интерпретация")
    bullets(
        s,
        [
            "Recall@10 = 1,00: ожидаемый источник всегда в десятке — конвейер работает",
            "Citation precision 0,88: около 12% ссылок лишние — усилить валидатор",
            "Correctness 0,94 и groundedness 0,95: ответы согласованы с контекстом",
            "No-answer precision 0,91: есть ложные отказы — расширить набор",
            "E2E p95 6,2 с: нужен прогресс в UI и асинхронные сценарии",
            "Вывод: ассистент для пилота, а не «полная автоматизация»",
        ],
        size=17,
    )
    add_footer(s, len(prs.slides))
    notes(s, "8:30–9:10. Не продавать метрики: объяснить, какие решения из них следуют.")

    # 11 value
    s = add_slide(prs, "Практическая ценность", "Потенциал применения")
    boxes = [
        ("Время", "Меньше поиска и переноса текста"),
        ("Качество", "Опора на корпус и цитаты"),
        ("Контроль", "Approval и атрибуция решений"),
        ("Аудит", "История без реконструкции"),
    ]
    for i, (h, t) in enumerate(boxes):
        left = 0.75 + (i % 2) * 6.0
        top = 1.55 + (i // 2) * 2.2
        textbox(
            s,
            h,
            left,
            top,
            5.7,
            1.0,
            24,
            True,
            WHITE,
            fill=NAVY if i % 2 == 0 else GREEN,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        textbox(
            s,
            t,
            left,
            top + 1.0,
            5.7,
            0.9,
            16,
            False,
            DARK,
            fill=LIGHT,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    textbox(
        s,
        "Условия пилота: ограниченное подразделение, политика ИИ, PII-маскирование, обучение, метрики пилота.",
        0.8,
        6.15,
        11.8,
        0.7,
        13,
        False,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    add_footer(s, len(prs.slides))
    notes(s, "9:10–9:40. Эффекты качественные; ROI считать в пилоте, а не по демо.")

    # 12 roadmap
    s = add_slide(prs, "Направления развития", "Потенциал · roadmap")
    rows = [
        ["Приоритет", "Направление", "Результат"],
        ["P0", "Лицензия и поддержка", "Условия поставки и SLA"],
        ["P0", "PII-маскирование", "Допуск в регулируемые отрасли"],
        ["P0", "UX в форме документа", "Порог входа"],
        ["P1", "Пилоты и кейсы", "Доказательства для тендеров"],
        ["P1", "Независимая экспертная оценка", "Снижение зависимости от судьи"],
        ["P2", "Отчёты, мастер шаблонов", "Сценарии методологов"],
        ["P2", "1С:ДО 3.0", "Расширение рынка"],
    ]
    table(s, rows, 0.8, 1.5, 11.7, 4.6, font=13)
    add_footer(s, len(prs.slides))
    notes(s, "9:40–9:50. P0 — условия эксплуатации, а не «фичи».")

    # Триггеры и границы MVP
    s = add_slide(prs, "Триггеры: что запускает агента", "Границы MVP")
    rows = [
        ["Триггер", "Как возникает", "Статус"],
        ["Документ", "Внутренний или входящий; тип — атрибут события", "MVP"],
        ["Задача", "Поставлена самому себе или пришла из процесса", "MVP"],
        ["Регламент", "Таймер по должностным обязанностям", "Цель, не MVP"],
    ]
    table(s, rows, 0.8, 1.5, 11.7, 2.8, font=14)
    textbox(
        s,
        "Для расширения внутренний и внешний документ — одно событие. Различия только в атрибутах, не в сценарии.",
        0.8,
        4.55,
        11.7,
        0.7,
        15,
        False,
        DARK,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    add_footer(s, len(prs.slides))
    notes(
        s,
        "Слайды Собственника — штатный процесс 1С:ДО и источник триггера, а не работа агента. Таймер по обязанностям — цель.",
    )

    # Синтетический корпус
    s = add_slide(prs, "Корпус как топливо", "Границы MVP")
    for i, (h, t) in enumerate(
        [
            ("Генерация", "Агент предлагает документы без жёсткой схемы."),
            ("Контроль", "Человек одобряет или возвращает на доработку."),
            ("Автоодобрение", "Временный ускоритель набора данных."),
        ]
    ):
        left = 0.8 + i * 4.0
        textbox(
            s,
            h,
            left,
            1.6,
            3.7,
            0.6,
            20,
            True,
            WHITE,
            fill=ORANGE if h == "Автоодобрение" else NAVY,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        textbox(
            s,
            t,
            left,
            2.2,
            3.7,
            1.3,
            14,
            False,
            DARK,
            fill=LIGHT,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    textbox(
        s,
        "В целевой системе автоодобрения нет: изменяющие действия подтверждает человек.",
        0.8,
        4.5,
        11.8,
        0.8,
        16,
        True,
        NAVY,
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    add_footer(s, len(prs.slides))
    notes(
        s,
        "Свободная генерация и автоодобрение — инструменты накопления корпуса, а не целевой режим.",
    )

    # 13 limitations
    s = add_slide(prs, "Ограничения: говорим честно", "Риски")
    bullets(
        s,
        [
            "PII-маскирование не реализовано",
            "Целевые шаблоны с поиском и фильтрами — проект",
            "Регламентный триггер по обязанностям — не реализован",
            "Автоодобрение — временный режим MVP, не цель",
            "Мастер шаблонов, вычитка и отчёты — проект",
            "Лицензия и поддержка/SLA не зафиксированы",
            "Совместимость с 1С:ДО 3.0 не подтверждена",
            "Метрики ограничены курируемым набором",
        ],
        size=17,
    )
    add_footer(s, len(prs.slides))
    notes(s, "9:50–9:55. Риски названы заранее — это повышает доверие комиссии.")

    # 14 conclusions
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = NAVY
    textbox(s, "Итог", 0.8, 0.9, 11.8, 0.5, 16, True, GREEN)
    textbox(
        s,
        "Контролируемый ИИ-контур\nвстроен в документооборот",
        0.8,
        1.5,
        11.8,
        1.7,
        34,
        True,
        WHITE,
    )
    bullets(
        s,
        [
            "Источники и цитаты вместо «чёрного ящика»",
            "Approval для изменяющих действий",
            "История: кто, что, когда, с каким результатом",
            "MVP — фундамент; цель — шаблоны с поиском и фильтрами",
            "Пилот — следующий шаг; PII и поддержка — P0",
        ],
        top=3.7,
        size=20,
        color=WHITE,
    )
    textbox(s, "Спасибо за внимание", 0.8, 6.45, 11.8, 0.5, 18, True, RGBColor(0xB9, 0xC9, 0xD6))
    notes(s, "9:55–10:00. Вывод и переход к вопросам.")

    # backup slides
    s = add_slide(prs, "Резерв: модель данных", "Backup")
    rows = [
        ["Объект", "Назначение"],
        ["АИС_ЗапускиАгентов", "Состояние, шаги, approval"],
        ["АИС_ВзаимодействияИИ", "Запросы и ответы"],
        ["АИС_ИсторияДействийИИ", "Аудит, пользователь, результат"],
        ["АИС_НастройкиАгента", "Персональные настройки"],
        ["АИС_ДокументыВПапках", "Документ ↔ папка ↔ сотрудник"],
    ]
    table(s, rows, 0.8, 1.5, 11.7, 3.8, font=13)
    add_footer(s, len(prs.slides))
    notes(s, "Ответ на вопрос о модели данных.")

    s = add_slide(prs, "Резерв: протокол шага", "Backup")
    bullets(
        s,
        [
            "POST /v1/agent/step, один tool_call или final",
            "protocol_version и run_version; устаревшие ответы отклоняются",
            "1С проверяет allowlist и аргументы",
            "Approval: subject_kind, tool, хеш аргументов",
            "Повторный вызов возвращает сохранённый результат",
            "Все шаги — в истории с длительностью и статусом",
        ],
        size=17,
    )
    add_footer(s, len(prs.slides))
    notes(s, "Ответ на вопрос о протоколе и идемпотентности.")

    s = add_slide(prs, "Резерв: позиционирование", "Backup")
    rows = [
        ["Критерий", "ai_scrivener", "«Неонис»", "Встроенный ИИ 1С"],
        ["RAG по корпусу", "Реализован", "Заявлен", "Не для черновиков"],
        ["Агентские действия", "Да, approval", "н/д", "Ограничены"],
        ["Аудит и авторство", "Да", "н/д", "н/д"],
        ["Частный контур", "Да", "н/д", "Да"],
        ["Лицензия/поддержка", "Не зафиксированы", "Платная", "1С"],
    ]
    table(s, rows, 0.8, 1.5, 11.7, 3.6, font=12)
    add_footer(s, len(prs.slides))
    notes(s, "Ответ на вопрос о конкурентах; данные по конкурентам — публичные и требуют проверки.")

    path = OUT / "02_Презентация_ИАР.pptx"
    prs.save(path)
    print(f"PPTX {path.name:45s} {path.stat().st_size / 1024:8.1f} KB")
    return path


def convert_pptx(pptx: Path) -> Path:
    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", str(OUT), str(pptx)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pdf = OUT / (pptx.stem + ".pdf")
    print(f"PDF  {pdf.name:45s} {pdf.stat().st_size / 1024:8.1f} KB")
    return pdf


OWNER_DECK = ROOT / "docs" / "iar" / "presentation" / "extension-presentation.html"


def build_html_presentation() -> tuple[Path, Path]:
    """Берёт актуальную HTML-презентацию и делает автономный HTML + PDF."""
    html = OWNER_DECK.read_text(encoding="utf-8")

    def embed(match: re.Match[str]) -> str:
        rel = match.group(1)
        image = OWNER_DECK.parent / "screenshots" / rel
        data = base64.b64encode(image.read_bytes()).decode("ascii")
        return f'src="data:image/png;base64,{data}"'

    html = re.sub(r'src="screenshots/([^"]+)"', embed, html)
    html_path = OUT / "02_Презентация_ИАР.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path = OUT / "02_Презентация_ИАР.pdf"
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=15000",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    legacy = OUT / "02_Презентация_ИАР.pptx"
    legacy.unlink(missing_ok=True)
    print(f"HTML {html_path.name:45s} {html_path.stat().st_size / 1024:8.1f} KB")
    print(f"PDF  {pdf_path.name:45s} {pdf_path.stat().st_size / 1024:8.1f} KB")
    return html_path, pdf_path


def make_zip(files: list[Path]) -> Path:
    zip_path = OUT / "ИАР_комплект_без_видео.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)
        for src in sorted(DOCS.glob("*.md")):
            z.write(src, "sources/" + src.name)
        z.write(DOCS / "build_iar.py", "sources/build_iar.py")
        for asset in sorted((DOCS / "assets").glob("*.png")):
            z.write(asset, "sources/assets/" + asset.name)
        analyst = [
            "docs/system-analysis/view-and-scope.md",
            "docs/system-analysis/stakeholder-map.md",
            "docs/system-analysis/glossary.md",
            "docs/system-analysis/use-cases.md",
            "docs/system-analysis/c4-model.md",
            "docs/system-analysis/competitive_analysis.md",
            "docs/process-diagrams.md",
            "docs/data-model.md",
            "docs/ai-agent-protocol.md",
            "docs/requirements/functional_requirements.md",
            "docs/requirements/nonfunctional_requirements.md",
            "docs/requirements/traceability_matrix.md",
            "guides/runbook.md",
            "tests/1c/test_access.md",
            "tests/1c/test_agent.md",
            "tests/1c/test_obligations.md",
            "tests/1c/test_prompts.md",
            "artifacts/llm-eval/full-gigachat3pro.md",
        ]
        for rel in analyst:
            path = ROOT / rel
            if path.exists():
                z.write(path, "analyst/" + rel)
    print(f"ZIP  {zip_path.name:45s} {zip_path.stat().st_size / 1024:8.1f} KB")
    return zip_path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = []
    mapping = [
        ("00_passport.md", "00_Паспорт_ИАР.pdf"),
        ("01_report.md", "01_Пояснительная_записка_ИАР.pdf"),
        ("03_demo_scenario.md", "03_Сценарий_демонстрации.pdf"),
        ("05_analyst_package.md", "05_Реестр_артефактов_СА.pdf"),
        ("06_appendices.md", "06_Приложения_ИАР.pdf"),
        ("07_cover_documents.md", "07_Сопроводительные_документы.pdf"),
        ("02_presentation_outline.md", "02_Структура_презентации.pdf"),
    ]
    for src, dst in mapping:
        pdf = OUT / dst
        html_to_pdf(DOCS / src, pdf)
        pdfs.append(pdf)

    html_pres, pres_pdf = build_html_presentation()
    pdfs.append(pres_pdf)

    shutil.copy2(DOCS / "README.md", OUT / "README.md")
    files = [*pdfs, html_pres, OUT / "README.md"]
    make_zip(files)
    print("\nГотово:", OUT)


if __name__ == "__main__":
    main()
