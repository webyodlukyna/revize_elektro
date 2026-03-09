# vytvořil lukyn.sifty@gmail.com copyright 2025
"""
export.py – Export revizí do PDF
=================================
Používá reportlab pro generování PDF bez externích závislostí.
"""

import io
import os
from datetime import date, datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ─── Barvy ────────────────────────────────────────────────────────────────────
BARVA_HLAVICKA  = colors.HexColor("#2c3e50")
BARVA_PROSLA    = colors.HexColor("#e74c3c")
BARVA_VAROVANI  = colors.HexColor("#e67e22")
BARVA_OK        = colors.HexColor("#27ae60")
BARVA_RADEK_1   = colors.HexColor("#f8f9fa")
BARVA_RADEK_2   = colors.white
BARVA_TEXT      = colors.HexColor("#2c3e50")


def _configure_pdf_fonts() -> tuple[str, str]:
    """Vrátí (regular, bold) font name použitelné pro češtinu v PDF."""
    # Primárně použijeme fonty dodávané s ReportLabem (stabilní napříč prostředími).
    try:
        import reportlab

        rl_fonts_dir = Path(reportlab.__file__).resolve().parent / "fonts"
        vera_regular = rl_fonts_dir / "Vera.ttf"
        vera_bold = rl_fonts_dir / "VeraBd.ttf"

        if vera_regular.exists() and vera_bold.exists():
            regular_name = "Vera"
            bold_name = "Vera-Bold"

            registered = set(pdfmetrics.getRegisteredFontNames())
            if regular_name not in registered:
                pdfmetrics.registerFont(TTFont(regular_name, str(vera_regular)))
            if bold_name not in registered:
                pdfmetrics.registerFont(TTFont(bold_name, str(vera_bold)))

            return regular_name, bold_name
    except Exception:
        pass

    candidates = [
        # Windows
        (
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "ArialUnicode",
            "ArialUnicode-Bold",
        ),
        # Linux
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "DejaVuSans",
            "DejaVuSans-Bold",
        ),
        # macOS
        (
            "/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "ArialMacUnicode",
            "ArialMacUnicode-Bold",
        ),
    ]

    for regular_path, bold_path, regular_name, bold_name in candidates:
        if os.path.exists(regular_path) and os.path.exists(bold_path):
            try:
                registered = set(pdfmetrics.getRegisteredFontNames())
                if regular_name not in registered:
                    pdfmetrics.registerFont(TTFont(regular_name, regular_path))
                if bold_name not in registered:
                    pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                return regular_name, bold_name
            except Exception:
                continue

    # Fallback funguje, ale nemusí pokrýt všechnu diakritiku.
    return "Helvetica", "Helvetica-Bold"


def _ics_escape(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _stav_barva(datum_platnosti: str) -> tuple[str, colors.Color]:
    """Vrátí text stavu a barvu pro PDF."""
    plat  = datetime.strptime(datum_platnosti, "%Y-%m-%d").date()
    zbyvá = (plat - date.today()).days
    if zbyvá < 0:
        return f"Prošlá ({abs(zbyvá)} dní)", BARVA_PROSLA
    elif zbyvá <= 7:
        return f"Za {zbyvá} dní", BARVA_VAROVANI
    elif zbyvá <= 30:
        return f"Za {zbyvá} dní", BARVA_VAROVANI
    else:
        return f"Za {zbyvá} dní", BARVA_OK


def _fmt(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y") if d else "—"


def generuj_pdf(revize: list[dict], filtr: str = "Všechny") -> bytes:
    """
    Vygeneruje PDF s přehledem revizí a vrátí ho jako bytes.

    Args:
        revize: seznam revizí (dict) z database.get_all()
        filtr:  popis použitého filtru (zobrazí se v hlavičce)

    Returns:
        PDF soubor jako bytes (vhodné pro st.download_button)
    """
    buffer = io.BytesIO()
    font_regular, font_bold = _configure_pdf_fonts()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="Přehled revizí – RP ELECTRIC SOLUTION s.r.o.",
        author="Systém hlídání revizí",
    )

    styles = getSampleStyleSheet()

    nadpis_style = ParagraphStyle(
        "Nadpis",
        parent=styles["Normal"],
        fontSize=18,
        textColor=BARVA_HLAVICKA,
        spaceAfter=2 * mm,
        fontName=font_bold,
    )
    podnadpis_style = ParagraphStyle(
        "Podnadpis",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#7f8c8d"),
        spaceAfter=6 * mm,
        fontName=font_regular,
    )
    legenda_style = ParagraphStyle(
        "Legenda",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#7f8c8d"),
        fontName=font_regular,
        spaceBefore=4 * mm,
    )

    # ─── Obsah dokumentu ──────────────────────────────────────────────────────
    prvky = []

    # Hlavička
    prvky.append(Paragraph("Přehled revizí - RP ELECTRIC SOLUTION s.r.o.", nadpis_style))
    dnes_txt = date.today().strftime("%d.%m.%Y")
    prvky.append(Paragraph(
        f"Vygenerováno: {dnes_txt}  ·  Filtr: {filtr}  ·  Celkem záznamů: {len(revize)}",
        podnadpis_style,
    ))
    prvky.append(HRFlowable(width="100%", thickness=1, color=BARVA_HLAVICKA, spaceAfter=4 * mm))

    if not revize:
        prvky.append(Paragraph("Žádné revize k zobrazení.", styles["Normal"]))
    else:
        # Záhlaví tabulky
        hlavicka = ["#", "Zařízení / Objekt", "Umístění", "Typ", "Provedena", "Platnost do", "Technik", "Stav"]

        sirky = [
            8  * mm,   # #
            42 * mm,   # Zařízení
            28 * mm,   # Umístění
            20 * mm,   # Typ
            22 * mm,   # Provedena
            22 * mm,   # Platnost
            28 * mm,   # Technik
            26 * mm,   # Stav
        ]

        radky = [hlavicka]
        barvy_stavu = []

        for i, r in enumerate(revize):
            stav_txt, stav_barva = _stav_barva(r["datum_platnosti"])
            barvy_stavu.append(stav_barva)
            radky.append([
                str(i + 1),
                r.get("nazev") or "—",
                r.get("umisteni") or "—",
                r.get("typ") or "—",
                _fmt(r.get("datum_revize", "")),
                _fmt(r.get("datum_platnosti", "")),
                r.get("revizni_technik") or "—",
                stav_txt,
            ])

        tabulka = Table(radky, colWidths=sirky, repeatRows=1)

        # Styl tabulky
        ts = TableStyle([
            # Záhlaví
            ("BACKGROUND",    (0, 0), (-1, 0), BARVA_HLAVICKA),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), font_bold),
            ("FONTSIZE",      (0, 0), (-1, 0), 8),
            ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("TOPPADDING",    (0, 0), (-1, 0), 4),

            # Datové řádky
            ("FONTNAME",  (0, 1), (-1, -1), font_regular),
            ("FONTSIZE",  (0, 1), (-1, -1), 7.5),
            ("ALIGN",     (0, 1), (0, -1),  "CENTER"),   # číslo
            ("ALIGN",     (7, 1), (7, -1),  "CENTER"),   # stav
            ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),

            # Mřížka
            ("GRID",      (0, 0), (-1, -1), 0.4, colors.HexColor("#dee2e6")),
            ("LINEBELOW", (0, 0), (-1, 0),  0.8, BARVA_HLAVICKA),
        ])

        # Střídání barev řádků + barva stavu
        for i in range(1, len(radky)):
            bg = BARVA_RADEK_1 if i % 2 == 0 else BARVA_RADEK_2
            ts.add("BACKGROUND", (0, i), (6, i), bg)
            # Sloupec stavu — barevný text
            ts.add("TEXTCOLOR",  (7, i), (7, i), barvy_stavu[i - 1])
            ts.add("FONTNAME",   (7, i), (7, i), font_bold)

        tabulka.setStyle(ts)
        prvky.append(tabulka)

        # Legenda
        prvky.append(Paragraph(
            "Legenda:  "
            "<font color='#e74c3c'>■ Prošlá</font>  ·  "
            "<font color='#e67e22'>■ Do 30 dní</font>  ·  "
            "<font color='#27ae60'>■ V pořádku</font>",
            legenda_style,
        ))

    # ─── Generování ───────────────────────────────────────────────────────────
    doc.build(prvky)
    buffer.seek(0)
    return buffer.read()


def generuj_ics(revize: list[dict], calendar_name: str = "RP ELECTRIC SOLUTION s.r.o. – Revize") -> bytes:
    """Vygeneruje iCalendar (.ics) s termíny platnosti revizí."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//RP ELECTRIC SOLUTION s.r.o.//Revize//CS",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]

    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for r in revize:
        try:
            due = datetime.strptime(r.get("datum_platnosti", ""), "%Y-%m-%d").date()
        except Exception:
            continue

        uid = f"revize-{r.get('id', 'x')}-{due.strftime('%Y%m%d')}@rp-electric-solution.local"
        dtstart = due.strftime("%Y%m%d")
        dtend = due.fromordinal(due.toordinal() + 1).strftime("%Y%m%d")

        summary = f"Revize: {r.get('nazev') or 'Bez názvu'}"
        description_parts = [
            f"Typ: {r.get('typ') or '—'}",
            f"Technik: {r.get('revizni_technik') or '—'}",
            f"Platnost: {due.strftime('%d.%m.%Y')}",
            f"Poznámka: {r.get('poznamka') or '—'}",
        ]
        description = "\\n".join(description_parts)

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(uid)}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"LOCATION:{_ics_escape(r.get('umisteni') or '')}",
            f"DESCRIPTION:{_ics_escape(description)}",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    content = "\r\n".join(lines) + "\r\n"
    return content.encode("utf-8")
