"""
PDF Generator — Branded business report generation using ReportLab.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import structlog

logger = structlog.get_logger("pdf_generator")


class PDFGenerator:
    """Generates branded PDF reports for the ReportAgent."""

    BRAND_COLOR = (0.06, 0.08, 0.12)       # dark near-black
    ACCENT_COLOR = (0.84, 0.67, 0.27)      # gold
    TEXT_COLOR = (0.15, 0.15, 0.20)
    LIGHT_BG = (0.97, 0.97, 0.98)

    async def generate_business_report(
        self,
        output_path: Path,
        metrics: object,
        narrative: str,
        period_start: datetime,
        period_end: datetime,
    ) -> None:
        """Generate a complete business performance PDF report."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                HRFlowable,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError:
            logger.warning("reportlab_not_installed", msg="pip install reportlab")
            # Create a minimal text file as fallback
            with open(output_path, "w") as f:
                f.write(f"Business Report: {period_start.date()} to {period_end.date()}\n\n")
                f.write(narrative)
            return

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        brand_dark = colors.Color(*self.BRAND_COLOR)
        brand_gold = colors.Color(*self.ACCENT_COLOR)

        title_style = ParagraphStyle(
            "Title",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=brand_dark,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=11,
            textColor=colors.Color(0.5, 0.5, 0.5),
            spaceAfter=20,
        )
        heading_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=13,
            textColor=brand_dark,
            spaceBefore=16,
            spaceAfter=8,
            fontName="Helvetica-Bold",
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.Color(*self.TEXT_COLOR),
            spaceAfter=8,
            leading=16,
        )

        story = []

        # Header
        story.append(Paragraph("AI Autopilot", title_style))
        story.append(Paragraph(
            f"Weekly Business Report • {period_start.strftime('%B %d')} – {period_end.strftime('%B %d, %Y')}",
            subtitle_style,
        ))
        story.append(HRFlowable(width="100%", thickness=2, color=brand_gold))
        story.append(Spacer(1, 16))

        # Executive Summary
        story.append(Paragraph("Executive Summary", heading_style))
        story.append(Paragraph(narrative, body_style))
        story.append(Spacer(1, 12))

        # KPI Table
        story.append(Paragraph("Key Performance Indicators", heading_style))

        kpi_data = [
            ["Metric", "This Period", "Status"],
            ["Monthly Recurring Revenue", f"${getattr(metrics, 'mrr', 0):,.0f}", "—"],
            ["New Revenue Collected", f"${getattr(metrics, 'new_revenue', 0):,.0f}", "—"],
            ["Outstanding Invoices", f"${getattr(metrics, 'outstanding_invoices', 0):,.0f}", "—"],
            ["New Leads", str(getattr(metrics, "new_leads", 0)), "—"],
            ["Qualified Leads", str(getattr(metrics, "qualified_leads", 0)), "—"],
            ["Deals Closed", str(getattr(metrics, "deals_closed", 0)), "—"],
            ["Pipeline Value", f"${getattr(metrics, 'pipeline_value', 0):,.0f}", "—"],
            ["Lead-to-Close Rate", f"{getattr(metrics, 'lead_to_close_rate', 0):.1f}%", "—"],
        ]

        table = Table(kpi_data, colWidths=[8 * cm, 5 * cm, 4 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), brand_dark),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.96, 0.96, 0.98)]),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWHEIGHT", (0, 0), (-1, -1), 22),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.88, 0.88, 0.92)),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)
        story.append(Spacer(1, 16))

        # Footer
        story.append(HRFlowable(width="100%", thickness=1, color=colors.Color(0.85, 0.85, 0.88)))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"Generated by AI Autopilot • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8,
                           textColor=colors.Color(0.6, 0.6, 0.65)),
        ))

        doc.build(story)
        logger.info("pdf_report_built", path=str(output_path))
