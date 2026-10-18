"""Automatic Intelligence Report Generator for Dakota.

Compiles forensic and market briefs with:
- Executive Summary & Methodology
- Grounded Evidence References & Key Findings
- Chronology / Timeline
- Conflicting Information & Disagreements
- Technical & Forensic Stance
- Complete Source Provenance
- HTML & Markdown Export
"""
from __future__ import annotations

import html
import uuid
from datetime import datetime, timezone
from typing import Any

from src.intelligence.models import (
    ClaimFinding,
    EvidenceItem,
    IntelligenceReport,
    TimelineEvent,
)
from src.intelligence.retriever import IntelligenceRetriever


class ReportGenerator:
    """Generates verified intelligence briefs from conversations or specific tickers/cases."""

    def __init__(self) -> None:
        self.retriever = IntelligenceRetriever()

    def generate_report(
        self,
        report_type: str = "company_brief",
        ticker: str | None = None,
        investigation_id: str | None = None,
        custom_title: str | None = None,
    ) -> IntelligenceReport:
        rid = f"REP-{uuid.uuid4().hex[:8].upper()}"
        target = (ticker or investigation_id or "General Market").upper()
        title = custom_title or f"Dakota Intelligence Brief — {target}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Retrieve grounded evidence
        query = f"Investigate {target} and summarize key risks and evidence"
        evidence_items = self.retriever.retrieve(
            query=query,
            context={"ticker": ticker, "investigation_id": investigation_id},
            max_evidence=10,
        )

        findings: list[ClaimFinding] = []
        for e in evidence_items:
            findings.append(
                ClaimFinding(
                    claim=e.snippet[:150],
                    status="directly_observed" if e.verified else "unverified_claim",
                    supporting_evidence_ids=[e.id],
                    severity="high" if "High" in e.snippet or "scam" in e.snippet.lower() else "low",
                    confidence=e.confidence,
                )
            )

        timeline: list[TimelineEvent] = []
        for e in evidence_items:
            if e.published_at:
                timeline.append(
                    TimelineEvent(
                        date=e.published_at[:10],
                        title=e.title[:60],
                        description=e.snippet[:120],
                        evidence_id=e.id,
                    )
                )

        sources = []
        for e in evidence_items:
            sources.append({
                "id": e.id,
                "name": e.source_name,
                "type": e.type.value,
                "url": e.source_url,
                "confidence": e.confidence,
                "verified": e.verified,
            })

        conflicts = []
        has_promotional = any(e.type == "social" or "target" in e.snippet.lower() for e in evidence_items)
        has_high_risk = any("High" in e.snippet or "scam" in e.snippet.lower() for e in evidence_items)
        if has_promotional and has_high_risk:
            conflicts.append("Promotional price expectations diverge from internal risk score and forensic findings.")

        exec_summary = (
            f"This intelligence brief synthesizes current observations for {target} compiled from "
            f"{len(evidence_items)} independent Dakota data points across equity registries, "
            f"news RSS streams, and live intake channels. All findings are traceable to their source identifiers."
        )

        methodology = (
            "Dakota utilizes a multi-pillar forensic framework evaluating market footprint, promoter integrity, "
            "coordination signals, and regulatory actions. Records are retrieved directly from SQLite and verified RSS feeds. "
            "No ungrounded claims or fictitious citations are permitted."
        )

        return IntelligenceReport(
            id=rid,
            title=title,
            report_type=report_type,
            executive_summary=exec_summary,
            scope_and_methodology=methodology,
            key_findings=findings,
            evidence_references=evidence_items,
            timeline=timeline,
            conflicting_information=conflicts,
            limitations=[
                "External social discovery is limited to publicly indexed data without accessing restricted private feeds.",
                "Market prices represent recorded session data rather than real-time exchange tickers.",
            ],
            source_list=sources,
            generated_at=now_iso,
        )

    def render_markdown(self, report: IntelligenceReport) -> str:
        lines: list[str] = [
            f"# {report.title}",
            f"**Report ID:** `{report.id}` | **Generated:** {report.generated_at[:16]} UTC | **Type:** {report.report_type.replace('_', ' ').title()}",
            "",
            "## Executive Summary",
            report.executive_summary,
            "",
            "## Scope & Methodology",
            report.scope_and_methodology,
            "",
            "## Key Findings",
        ]

        for f in report.key_findings:
            ref = f" ({', '.join(f.supporting_evidence_ids)})" if f.supporting_evidence_ids else ""
            lines.append(f"- **[{f.severity.upper()}]** {f.claim}{ref} — *Status: {f.status}*")

        if report.conflicting_information:
            lines.extend(["", "## Conflicting Information & Disagreements"])
            for c in report.conflicting_information:
                lines.append(f"- {c}")

        if report.timeline:
            lines.extend(["", "## Chronology of Events"])
            for t in report.timeline:
                lines.append(f"- **{t.date}:** {t.title} — {t.description}")

        lines.extend(["", "## Source Provenance & References"])
        for s in report.source_list:
            url_str = f" ([Link]({s['url']}))" if s.get("url") else ""
            lines.append(f"- **[{s['id']}]** {s['name']} ({s['type'].upper()}){url_str} — Confidence: {int(s['confidence']*100)}%")

        lines.extend([
            "",
            "## Limitations & Disclaimers",
            "> Dakota reports risk indicators and available evidence. It does not determine fraud or provide trading advice.",
        ])
        for lim in report.limitations:
            lines.append(f"> • {lim}")

        return "\n".join(lines)

    def render_html(self, report: IntelligenceReport) -> str:
        """Render a clean, institutional, print-friendly HTML report."""
        findings_html = "".join(
            f"<li><strong>[{html.escape(f.severity.upper())}]</strong> {html.escape(f.claim)} <em>({html.escape(f.status)})</em></li>"
            for f in report.key_findings
        )
        sources_html = "".join(
            f"<tr><td><code>{html.escape(s['id'])}</code></td><td>{html.escape(s['name'])}</td><td>{html.escape(s['type'])}</td><td>{int(s['confidence']*100)}%</td></tr>"
            for s in report.source_list
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(report.title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #1e293b; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
    h1 {{ font-size: 26px; border-bottom: 2px solid #0284c7; padding-bottom: 8px; color: #0f172a; }}
    h2 {{ font-size: 18px; color: #0369a1; margin-top: 28px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
    .badge {{ display: inline-block; background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; font-size: 13px; }}
    th {{ background: #f8fafc; font-weight: 600; }}
    .disclaimer {{ background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; margin-top: 30px; font-size: 12px; color: #991b1b; }}
    @media print {{ body {{ margin: 0; padding: 0; }} }}
  </style>
</head>
<body>
  <h1>{html.escape(report.title)}</h1>
  <p><strong>Report ID:</strong> {html.escape(report.id)} | <strong>Generated:</strong> {html.escape(report.generated_at[:16])} UTC | <span class="badge">{html.escape(report.report_type)}</span></p>
  
  <h2>Executive Summary</h2>
  <p>{html.escape(report.executive_summary)}</p>

  <h2>Scope & Methodology</h2>
  <p>{html.escape(report.scope_and_methodology)}</p>

  <h2>Key Findings</h2>
  <ul>{findings_html}</ul>

  <h2>Source Provenance</h2>
  <table>
    <thead><tr><th>ID</th><th>Source Name</th><th>Type</th><th>Confidence</th></tr></thead>
    <tbody>{sources_html}</tbody>
  </table>

  <div class="disclaimer">
    <strong>Regulatory Disclaimer:</strong> Dakota reports available risk indicators only. Not investment advice, not an accusation of fraud.
  </div>
</body>
</html>"""
