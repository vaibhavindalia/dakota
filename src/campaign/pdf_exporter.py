"""Institutional PDF Exporter for Dakota Forensic Campaign Dossiers.

Generates multi-page, publication-quality, branded PDF dossiers using ReportLab
with running headers, dynamic 'Page X of Y' numbering, structured tables,
and robust Unicode/currency sanitization.
"""
from __future__ import annotations

import html
import io
import re
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _clean_text_for_pdf(text: Any) -> str:
    """Sanitize strings for standard ReportLab Helvetica fonts."""
    if text is None:
        return "N/A"
    s = str(text)
    # Replace Indian currency symbol with Rs.
    s = s.replace("₹", "Rs. ")
    # Replace common Unicode quotes and dashes with ASCII
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("—", " - ").replace("–", " - ").replace("•", "*")
    # Strip emojis or unencodable chars above \u00ff
    s = re.sub(r"[^\x00-\xff]", "", s)
    return html.escape(s)


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and draw 'Page X of Y' and headers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[Any] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Running Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 800, "DAKOTA FINANCIAL INTELLIGENCE • FORENSIC CAMPAIGN DOSSIER")
            self.drawRightString(540, 800, "CONFIDENTIAL / REGULATORY REVIEW")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(54, 794, 540, 794)

        # Running Footer (all pages)
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(54, 45, 540, 45)

        footer_text = "Dakota Forensic Terminal | Automated Evidence Dossier | Not an official SEBI finding"
        self.drawString(54, 32, footer_text)
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(540, 32, page_str)
        self.restoreState()


def render_campaign_pdf(dossier: dict[str, Any]) -> bytes:
    """Render a comprehensive forensic campaign dossier into a downloadable PDF buffer."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Custom institutional typography
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )

    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0369a1"),
        spaceBefore=12,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
    )

    callout_style = ParagraphStyle(
        "Callout",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#7c2d12"),
    )

    table_header = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )

    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#334155"),
    )

    story: list[Any] = []

    # 1. Header Banner & Title
    tier = str(dossier.get("tier", "CANDIDATE")).upper()
    tier_bg = "#fee2e2" if tier == "HIGH" else ("#fef3c7" if tier == "MODERATE" else "#e0f2fe")
    tier_fg = "#991b1b" if tier == "HIGH" else ("#92400e" if tier == "MODERATE" else "#0369a1")

    banner_data = [
        [
            Paragraph("<strong>DAKOTA FORENSIC CAMPAIGN INTELLIGENCE DOSSIER</strong>", ParagraphStyle("Hdr", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#0284c7"))),
            Paragraph(f"<font color='{tier_fg}'><strong>[{tier} CONFIDENCE]</strong></font>", ParagraphStyle("HdrR", fontName="Helvetica-Bold", fontSize=9, alignment=2)),
        ]
    ]
    banner_table = Table(banner_data, colWidths=[340, 146])
    banner_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 4))

    story.append(Paragraph(_clean_text_for_pdf(dossier.get("title", "Forensic Campaign")), title_style))
    story.append(Spacer(1, 4))

    # Metadata Summary Bar
    dossier_id = _clean_text_for_pdf(dossier.get("dossier_id"))
    campaign_id = _clean_text_for_pdf(dossier.get("campaign_id"))
    status = _clean_text_for_pdf(dossier.get("status", "active")).upper()
    score = f"{int(float(dossier.get('confidence_score', 0.5)) * 100)}%"
    export_ts = _clean_text_for_pdf(str(dossier.get("exported_at_utc", ""))[:19].replace("T", " "))

    meta_text = (
        f"<b>Dossier ID:</b> {dossier_id} &nbsp;|&nbsp; "
        f"<b>Campaign ID:</b> {campaign_id} &nbsp;|&nbsp; "
        f"<b>Status:</b> {status} &nbsp;|&nbsp; "
        f"<b>Score:</b> {score} &nbsp;|&nbsp; "
        f"<b>Exported:</b> {export_ts} UTC"
    )
    story.append(Paragraph(meta_text, body_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284c7"), spaceAfter=10))

    # 2. Executive Summary & Forensic Scope
    story.append(Paragraph("1. Executive Summary & Correlation Scope", section_heading))
    method_text = (
        f"This dossier documents a cross-scrip promotional campaign detected across "
        f"<b>{len(dossier.get('securities', []))} securities</b> and "
        f"<b>{len(dossier.get('public_actors', []))} public promoter channels</b> over a "
        f"<b>{dossier.get('time_window_hours', 24)}-hour observation window</b>. "
        f"First observed activity: <code>{_clean_text_for_pdf(dossier.get('first_seen_utc'))}</code>; "
        f"latest observed activity: <code>{_clean_text_for_pdf(dossier.get('last_seen_utc'))}</code>."
    )
    story.append(Paragraph(method_text, body_style))
    story.append(Spacer(1, 6))

    # 3. Participating Securities Table
    story.append(Paragraph("2. Connected Securities & Market Telemetry", section_heading))
    sec_rows = [
        [
            Paragraph("Security", table_header),
            Paragraph("Exchange", table_header),
            Paragraph("Association Rationale", table_header),
            Paragraph("Observed Price / Vol", table_header),
            Paragraph("Telemetry Freshness", table_header),
        ]
    ]

    for s in dossier.get("securities", []):
        mkt = s.get("market_telemetry", {})
        price_str = f"Rs. {mkt.get('latest_price')}" if mkt.get("latest_price") is not None else "N/A"
        vol_str = f"Vol Ratio: {mkt.get('volume_ratio_20d')}x" if mkt.get("volume_ratio_20d") is not None else ""
        telemetry_display = f"{price_str}<br/>{vol_str}".strip("<br/>")

        reasons = "<br/>• ".join(_clean_text_for_pdf(r) for r in s.get("relationship_reasons", []))
        if reasons:
            reasons = f"• {reasons}"

        sec_rows.append([
            Paragraph(f"<b>{_clean_text_for_pdf(s.get('ticker'))}</b>", table_cell),
            Paragraph(_clean_text_for_pdf(s.get("exchange", "NSE/BSE")), table_cell),
            Paragraph(reasons, table_cell),
            Paragraph(telemetry_display or "Unverified", table_cell),
            Paragraph(f"<code>{_clean_text_for_pdf(mkt.get('data_freshness', 'unavailable')).upper()}</code>", table_cell),
        ])

    sec_table = Table(sec_rows, colWidths=[70, 55, 205, 86, 70])
    sec_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sec_table)
    story.append(Spacer(1, 10))

    # 4. Public Promoter Actors & Attribution
    story.append(Paragraph("3. Public Broadcast Channels & Promoters", section_heading))
    actor_rows = [
        [
            Paragraph("Channel / Handle", table_header),
            Paragraph("Platform", table_header),
            Paragraph("Attribution & Uncertainty Notice", table_header),
        ]
    ]
    for act in dossier.get("public_actors", []):
        actor_rows.append([
            Paragraph(f"<b>{_clean_text_for_pdf(act.get('identifier'))}</b>", table_cell),
            Paragraph(_clean_text_for_pdf(act.get("platform", "telegram")).upper(), table_cell),
            Paragraph(_clean_text_for_pdf(act.get("uncertainty_note", "")), table_cell),
        ])

    if len(actor_rows) > 1:
        act_table = Table(actor_rows, colWidths=[120, 60, 306])
        act_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(act_table)
    else:
        story.append(Paragraph("<i>No public channel handles identified.</i>", body_style))
    story.append(Spacer(1, 10))

    # 5. Corroborating Market Alerts
    story.append(Paragraph("4. Corroborating Exchange Alerts", section_heading))
    alerts = dossier.get("market_alerts", [])
    if alerts:
        alt_rows = [
            [
                Paragraph("Alert ID", table_header),
                Paragraph("Rule Name", table_header),
                Paragraph("Severity", table_header),
                Paragraph("Observed / Threshold", table_header),
                Paragraph("Observation Time", table_header),
            ]
        ]
        for a in alerts[:8]:
            trig = a.get("trigger_value")
            thresh = a.get("threshold_value")
            val_str = f"Obs: {trig} | Thr: {thresh}" if trig is not None else "Breach"
            alt_rows.append([
                Paragraph(f"<code>{_clean_text_for_pdf(a.get('alert_id'))}</code>", table_cell),
                Paragraph(_clean_text_for_pdf(a.get("rule_name", "Alert")), table_cell),
                Paragraph(f"<b>{_clean_text_for_pdf(a.get('severity', 'warning')).upper()}</b>", table_cell),
                Paragraph(_clean_text_for_pdf(val_str), table_cell),
                Paragraph(_clean_text_for_pdf(str(a.get("observation_timestamp", ""))[:19].replace("T", " ")), table_cell),
            ])

        alt_table = Table(alt_rows, colWidths=[100, 130, 66, 100, 90])
        alt_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(alt_table)
    else:
        story.append(Paragraph("<i>No corroborating market alerts recorded during this campaign window.</i>", body_style))
    story.append(Spacer(1, 10))

    # 6. Chronological Promotional Timeline & Provenance
    story.append(Paragraph("5. Chronological Promotional Evidence & Provenance", section_heading))
    events = dossier.get("promotional_events", [])
    if events:
        ev_rows = [
            [
                Paragraph("Event / ID", table_header),
                Paragraph("Security", table_header),
                Paragraph("Source", table_header),
                Paragraph("Publication Time", table_header),
                Paragraph("Summary / Findings", table_header),
            ]
        ]
        for ev in events[:10]:
            ev_rows.append([
                Paragraph(f"<code>{_clean_text_for_pdf(ev.get('event_id'))}</code>", table_cell),
                Paragraph(f"<b>{_clean_text_for_pdf(ev.get('ticker'))}</b>", table_cell),
                Paragraph(_clean_text_for_pdf(ev.get("source_label")), table_cell),
                Paragraph(_clean_text_for_pdf(str(ev.get("publication_timestamp", ""))[:19].replace("T", " ")), table_cell),
                Paragraph(_clean_text_for_pdf(ev.get("summary")), table_cell),
            ])

        ev_table = Table(ev_rows, colWidths=[80, 50, 86, 90, 180])
        ev_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(ev_table)
    else:
        story.append(Paragraph("<i>No individual promotional event records stored.</i>", body_style))
    story.append(Spacer(1, 10))

    # 7. JEV Analytical Assessment (if available)
    jev = dossier.get("jev_intelligence")
    if jev:
        story.append(Paragraph("6. JEV Model Forensic Assessment", section_heading))
        jev_text = (
            f"<b>Model:</b> <code>{_clean_text_for_pdf(jev.get('model_id'))}</code> &nbsp;|&nbsp; "
            f"<b>Classification:</b> <b>{_clean_text_for_pdf(jev.get('predicted_label'))}</b> &nbsp;|&nbsp; "
            f"<b>Confidence:</b> {int(float(jev.get('confidence', 0.0)) * 100)}%<br/>"
            f"<b>Executive Summary:</b> {_clean_text_for_pdf(jev.get('executive_summary'))}<br/>"
            f"<b>Evidence Tokens Cited:</b> <code>{', '.join(_clean_text_for_pdf(t) for t in jev.get('cited_evidence_tokens', []))}</code>"
        )
        jev_box = Table([[Paragraph(jev_text, body_style)]], colWidths=[486])
        jev_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(jev_box)
        story.append(Spacer(1, 10))

    # 8. Contradictions, Limitations & Investigator Notes
    story.append(Paragraph("7. Investigative Context, Contradictions & Audit Trail", section_heading))
    limitations = dossier.get("contradictions_and_limitations", [])
    contra_paragraphs = "<br/>".join(f"• {_clean_text_for_pdf(c)}" for c in limitations)
    contra_box = Table([[Paragraph(f"<b>Key Caveats & Unresolved Questions:</b><br/>{contra_paragraphs}", callout_style)]], colWidths=[486])
    contra_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ed")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#fdba74")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(contra_box)
    story.append(Spacer(1, 8))

    notes = dossier.get("investigator_notes")
    if notes:
        story.append(Paragraph("<b>Investigator Review Notes:</b>", body_style))
        story.append(Paragraph(f"<code>{_clean_text_for_pdf(notes)}</code>", body_style))
        story.append(Spacer(1, 8))

    # 9. Institutional Disclaimer Callout
    disclaimer_text = _clean_text_for_pdf(dossier.get("regulatory_disclaimer", ""))
    disc_box = Table([[Paragraph(f"<b>REGULATORY NOTICE:</b> {disclaimer_text}", ParagraphStyle("Disc", fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#475569")))]], colWidths=[486])
    disc_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(Spacer(1, 10))
    story.append(disc_box)

    # Build document with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()
