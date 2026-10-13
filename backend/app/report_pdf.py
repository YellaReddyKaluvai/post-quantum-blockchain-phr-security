"""
Hospital-format diagnostic report rendering.

Produces the printed laboratory report as a PDF using ReportLab. Two layouts
are supported, chosen by the panel's ``layout`` field in ``lab_catalog``:

``tabular``   Analyte panels (CBC, LFT, lipids, urine...) printed as a
              four-column result table — Investigation / Result / Unit /
              Biological Reference Interval — with results outside their
              interval flagged H or L, exactly as a laboratory analyser prints.

``narrative`` ECG and radiology, printed as headed prose sections in the
              order used for structured reporting (indication, technique,
              comparison, findings, impression).

Every report carries the letterhead, accession and report identifiers, the
patient and referring-clinician block, specimen and method metadata, the
performing technician, and a verification footer stating the SHA-256 digest
and post-quantum signature status. Page furniture (page x of y, "End of
Report") is drawn by ``_Canvas`` so it appears on every page.
"""

from datetime import datetime
from io import BytesIO
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

from app.lab_catalog import analytes_of, flag_for, resolve_ref

# Visual identity
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
ACCENT = colors.HexColor("#0E7490")
RULE = colors.HexColor("#CBD5E1")
BAND = colors.HexColor("#F1F5F9")
ALERT = colors.HexColor("#B91C1C")

HOSPITAL_NAME = "QuantumCare Hospital"
HOSPITAL_TAGLINE = "Department of Laboratory Medicine & Diagnostics"
HOSPITAL_ADDRESS = "Plot 14, Health City Road, Bengaluru 560103, Karnataka, India"
HOSPITAL_CONTACT = "Tel +91 80 4000 1200  ·  lab@quantumcare.health  ·  NABL Accredited (M-0000)"

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
TOP_BAND = 34 * mm     # room reserved for the letterhead on page 1
FOOT_BAND = 18 * mm


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Normal"], fontName="Helvetica-Bold",
                             fontSize=15, textColor=INK, leading=18),
        "tagline": ParagraphStyle("tagline", parent=base["Normal"], fontName="Helvetica",
                                  fontSize=7.5, textColor=MUTED, leading=10),
        "title": ParagraphStyle("title", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=11.5, textColor=INK, alignment=TA_CENTER, leading=14),
        "section": ParagraphStyle("section", parent=base["Normal"], fontName="Helvetica-Bold",
                                  fontSize=8.5, textColor=ACCENT, leading=11, spaceBefore=2, spaceAfter=2),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica",
                               fontSize=8.5, textColor=INK, leading=11),
        "cellb": ParagraphStyle("cellb", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=8.5, textColor=INK, leading=11),
        "small": ParagraphStyle("small", parent=base["Normal"], fontName="Helvetica",
                                fontSize=7.5, textColor=MUTED, leading=10),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName="Helvetica",
                               fontSize=9, textColor=INK, leading=13, alignment=TA_JUSTIFY),
        "note": ParagraphStyle("note", parent=base["Normal"], fontName="Helvetica-Oblique",
                               fontSize=7.5, textColor=MUTED, leading=10),
    }


class _Canvas(pdfcanvas.Canvas):
    """Canvas that stamps the letterhead, footer and 'page x of y' on every page."""

    def __init__(self, *args, **kwargs):
        self._header = kwargs.pop("header_data", {})
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._draw_letterhead()
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_letterhead(self):
        s = _styles()
        # Accent bar
        self.setFillColor(ACCENT)
        self.rect(0, PAGE_H - 6, PAGE_W, 6, stroke=0, fill=1)

        # Hospital identity
        self.setFillColor(INK)
        self.setFont("Helvetica-Bold", 15)
        self.drawString(MARGIN, PAGE_H - 24 * mm + 8 * mm, HOSPITAL_NAME)
        self.setFillColor(MUTED)
        self.setFont("Helvetica", 7.5)
        self.drawString(MARGIN, PAGE_H - 24 * mm + 3.6 * mm, HOSPITAL_TAGLINE)
        self.drawString(MARGIN, PAGE_H - 24 * mm, HOSPITAL_ADDRESS)
        self.drawString(MARGIN, PAGE_H - 24 * mm - 3.6 * mm, HOSPITAL_CONTACT)

        # Report identifiers, right aligned
        hd = self._header
        self.setFillColor(INK)
        self.setFont("Helvetica-Bold", 8.5)
        self.drawRightString(PAGE_W - MARGIN, PAGE_H - 24 * mm + 8 * mm,
                             f"REPORT NO: {hd.get('report_no', '—')}")
        self.setFont("Helvetica", 7.5)
        self.setFillColor(MUTED)
        self.drawRightString(PAGE_W - MARGIN, PAGE_H - 24 * mm + 3.6 * mm,
                             f"Accession: {hd.get('accession', '—')}")
        self.drawRightString(PAGE_W - MARGIN, PAGE_H - 24 * mm,
                             f"Reported: {hd.get('reported_at', '—')}")

        # Rule under the letterhead
        self.setStrokeColor(INK)
        self.setLineWidth(1.1)
        y = PAGE_H - TOP_BAND + 4 * mm
        self.line(MARGIN, y, PAGE_W - MARGIN, y)

    def _draw_footer(self, total: int):
        hd = self._header
        self.setStrokeColor(RULE)
        self.setLineWidth(0.6)
        self.line(MARGIN, FOOT_BAND + 4 * mm, PAGE_W - MARGIN, FOOT_BAND + 4 * mm)

        self.setFillColor(MUTED)
        self.setFont("Helvetica", 6.8)
        self.drawString(MARGIN, FOOT_BAND,
                        f"Patient: {hd.get('patient_name', '—')}  ·  {hd.get('patient_uid', '—')}"
                        f"  ·  Report {hd.get('report_no', '—')}")
        self.drawCentredString(PAGE_W / 2, FOOT_BAND - 3.4 * mm,
                               "This report is an electronically generated and cryptographically signed "
                               "document. Results relate only to the specimen received.")
        self.drawRightString(PAGE_W - MARGIN, FOOT_BAND,
                             f"Page {self._pageNumber} of {total}")


def _kv_block(rows: list[tuple[str, str, str, str]], s: dict) -> Table:
    """Two-column-pair key/value block used for the patient and specimen panels."""
    data = []
    for l1, v1, l2, v2 in rows:
        data.append([
            Paragraph(l1, s["small"]), Paragraph(v1 or "—", s["cellb"]),
            Paragraph(l2, s["small"]), Paragraph(v2 or "—", s["cellb"]),
        ])
    t = Table(data, colWidths=[24 * mm, 54 * mm, 26 * mm, 54 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.white),
    ]))
    return t


def _format_value(raw: Any) -> str:
    """Print integers without a trailing .0, and thousands separated."""
    text = str(raw).strip()
    try:
        num = float(text)
    except (TypeError, ValueError):
        return text
    if num.is_integer() and abs(num) >= 1000:
        return f"{int(num):,}"
    if num.is_integer():
        return str(int(num))
    return text


def _result_table(panel: dict, values: dict, sex: str, s: dict) -> list:
    """Build the Investigation/Result/Unit/Reference table, grouped by section."""
    header = [
        Paragraph("<b>INVESTIGATION</b>", s["small"]),
        Paragraph("<b>RESULT</b>", s["small"]),
        Paragraph("<b>UNIT</b>", s["small"]),
        Paragraph("<b>BIOLOGICAL REFERENCE INTERVAL</b>", s["small"]),
    ]
    data = [header]
    styles = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
        ("BOX", (0, 0), (-1, -1), 0.7, INK),
    ]
    # Header paragraphs need white text; rebuild them with an inverted style.
    inv = ParagraphStyle("inv", parent=s["small"], textColor=colors.white,
                         fontName="Helvetica-Bold", fontSize=7.2)
    data[0] = [Paragraph(t, inv) for t in
               ("INVESTIGATION", "RESULT", "UNIT", "BIOLOGICAL REFERENCE INTERVAL")]

    row = 1
    any_row = False
    for section in panel.get("sections", []):
        analytes = section.get("analytes", [])
        # Only print a section if at least one of its analytes was reported.
        present = [a for a in analytes if str(values.get(a["key"], "")).strip() != ""]
        if not present:
            continue

        data.append([Paragraph(section["title"].upper(), s["section"]), "", "", ""])
        styles += [
            ("SPAN", (0, row), (-1, row)),
            ("BACKGROUND", (0, row), (-1, row), BAND),
            ("TOPPADDING", (0, row), (-1, row), 4),
            ("BOTTOMPADDING", (0, row), (-1, row), 4),
        ]
        row += 1

        for a in present:
            any_row = True
            raw = values.get(a["key"])
            low, high, ref_text = resolve_ref(a, sex)
            flag = flag_for(raw, low, high)

            name = ("&nbsp;&nbsp;&nbsp;&nbsp;" if a.get("indent") else "") + a["name"]
            if a.get("computed"):
                name += ' <font size="6" color="#64748B">(calculated)</font>'

            shown = _format_value(raw)
            if flag:
                result_para = Paragraph(
                    f'<b>{shown}</b> <font color="#B91C1C"><b>{flag}</b></font>', s["cellb"])
                styles.append(("TEXTCOLOR", (1, row), (1, row), ALERT))
            else:
                result_para = Paragraph(f"<b>{shown}</b>", s["cellb"])

            data.append([
                Paragraph(name, s["cell"]),
                result_para,
                Paragraph(a.get("unit") or "", s["cell"]),
                Paragraph(ref_text or "—", s["cell"]),
            ])
            row += 1

            if a.get("note"):
                data.append([Paragraph(f'<i>{a["note"]}</i>', s["note"]), "", "", ""])
                styles += [("SPAN", (0, row), (-1, row)),
                           ("TOPPADDING", (0, row), (-1, row), 0),
                           ("BOTTOMPADDING", (0, row), (-1, row), 3)]
                row += 1

    if not any_row:
        return []

    t = Table(data, colWidths=[74 * mm, 30 * mm, 24 * mm, 50 * mm], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle(styles))
    return [t]


def _narrative_blocks(panel: dict, values: dict, sex: str, s: dict) -> list:
    """Headed prose sections for ECG and radiology reports."""
    flow: list = []

    # ECG measurement strip, printed as a compact table before the prose.
    measurements = panel.get("measurements") or []
    present = [m for m in measurements if str(values.get(m["key"], "")).strip() != ""]
    if present:
        head = ParagraphStyle("mh", parent=s["small"], textColor=colors.white,
                              fontName="Helvetica-Bold", fontSize=7.2)
        data = [[Paragraph(t, head) for t in ("MEASUREMENT", "RESULT", "UNIT", "REFERENCE")]]
        styles = [
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
            ("BOX", (0, 0), (-1, -1), 0.7, INK),
        ]
        for i, m in enumerate(present, start=1):
            low, high, ref_text = resolve_ref(m, sex)
            flag = flag_for(values.get(m["key"]), low, high)
            shown = _format_value(values.get(m["key"]))
            txt = f'<b>{shown}</b>' + (f' <font color="#B91C1C"><b>{flag}</b></font>' if flag else "")
            data.append([
                Paragraph(m["name"], s["cell"]),
                Paragraph(txt, s["cellb"]),
                Paragraph(m.get("unit") or "", s["cell"]),
                Paragraph(ref_text or "—", s["cell"]),
            ])
        t = Table(data, colWidths=[64 * mm, 34 * mm, 26 * mm, 54 * mm], repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle(styles))
        flow += [t, Spacer(1, 5 * mm)]

    for section in panel.get("sections", []):
        fields = section.get("fields", [])
        present_fields = [f for f in fields if str(values.get(f["key"], "")).strip() != ""]
        if not present_fields:
            continue

        block: list = [Paragraph(section["title"].upper(), s["section"])]
        block.append(Spacer(1, 1 * mm))
        for f in present_fields:
            text = str(values.get(f["key"], "")).strip()
            # Preserve the technician's line breaks in prose fields.
            safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        .replace("\n", "<br/>"))
            block.append(Paragraph(f'<b>{f["label"]}:</b> {safe}', s["body"]))
            block.append(Spacer(1, 1.6 * mm))
        block.append(Spacer(1, 2.5 * mm))
        flow.append(KeepTogether(block))

    return flow


def build_report_pdf(
    *,
    panel: dict[str, Any],
    values: dict[str, Any],
    patient: dict[str, Any],
    doctor: Optional[dict[str, Any]],
    technician: dict[str, Any],
    report_no: str,
    accession: str,
    collected_at: Optional[datetime],
    reported_at: datetime,
    remarks: Optional[str] = None,
    interpretation: Optional[str] = None,
    document_hash: Optional[str] = None,
    signature_algorithm: Optional[str] = None,
    kem_algorithm: Optional[str] = None,
) -> bytes:
    """Render one finalised laboratory report and return the PDF bytes."""
    s = _styles()
    buf = BytesIO()

    header_data = {
        "report_no": report_no,
        "accession": accession,
        "reported_at": reported_at.strftime("%d-%b-%Y %H:%M"),
        "patient_name": patient.get("full_name"),
        "patient_uid": patient.get("user_id"),
    }

    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=TOP_BAND, bottomMargin=FOOT_BAND + 8 * mm,
        title=f"{panel['name']} — {report_no}",
        author=HOSPITAL_NAME,
        subject=f"Laboratory report for {patient.get('user_id', '')}",
    )
    frame = Frame(MARGIN, FOOT_BAND + 8 * mm,
                  PAGE_W - 2 * MARGIN, PAGE_H - TOP_BAND - FOOT_BAND - 8 * mm,
                  id="body", showBoundary=0)
    doc.addPageTemplates([PageTemplate(id="report", frames=[frame])])

    flow: list = []

    # Patient / clinician identification
    age_sex = " / ".join(x for x in [patient.get("age_display") or "", patient.get("gender") or ""] if x)
    flow.append(_kv_block([
        ("Patient Name", patient.get("full_name", ""), "Patient ID", patient.get("user_id", "")),
        ("Age / Sex", age_sex, "Blood Group", patient.get("blood_group") or "Not recorded"),
        ("Referred By", doctor.get("display") if doctor else "Self / Not specified",
         "Referring ID", (doctor or {}).get("user_id") or "—"),
    ], s))
    flow.append(Spacer(1, 3 * mm))

    # Specimen / method metadata
    flow.append(_kv_block([
        ("Specimen", panel.get("specimen", ""), "Accession No", accession),
        ("Collected On", collected_at.strftime("%d-%b-%Y %H:%M") if collected_at else "—",
         "Reported On", reported_at.strftime("%d-%b-%Y %H:%M")),
        ("Method", panel.get("method", ""), "Department", panel.get("category", "")),
    ], s))
    flow.append(Spacer(1, 5 * mm))

    # Report title
    flow.append(Paragraph(panel["name"].upper(), s["title"]))
    flow.append(Spacer(1, 1.5 * mm))
    rule = Table([[""]], colWidths=[PAGE_W - 2 * MARGIN], rowHeights=[0.9])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), INK)]))
    flow.append(rule)
    flow.append(Spacer(1, 4 * mm))

    # Results
    if panel.get("layout") == "narrative":
        flow += _narrative_blocks(panel, values, patient.get("gender", ""), s)
    else:
        flow += _result_table(panel, values, patient.get("gender", ""), s)
    flow.append(Spacer(1, 4 * mm))

    if any(flag_for(values.get(a["key"]), *resolve_ref(a, patient.get("gender", ""))[:2])
           for a in analytes_of(panel)):
        flow.append(Paragraph(
            '<b>H</b> = above reference interval &nbsp;·&nbsp; <b>L</b> = below reference interval',
            s["note"]))
        flow.append(Spacer(1, 3 * mm))

    if interpretation:
        block = [Paragraph("INTERPRETATION", s["section"]), Spacer(1, 1.5 * mm),
                 Paragraph(interpretation, s["body"])]
        flow.append(KeepTogether(block))
        flow.append(Spacer(1, 4 * mm))

    if remarks:
        safe = (str(remarks).replace("&", "&amp;").replace("<", "&lt;")
                            .replace(">", "&gt;").replace("\n", "<br/>"))
        block = [Paragraph("TECHNICAL REMARKS", s["section"]), Spacer(1, 1.5 * mm),
                 Paragraph(safe, s["body"])]
        flow.append(KeepTogether(block))
        flow.append(Spacer(1, 4 * mm))

    # Signature / verification block, kept on one page.
    #
    # The SHA-256 digest is deliberately NOT printed here: the digest is taken
    # over these very bytes, so embedding it would change the value it claims
    # to be. The digest is stored alongside the record and shown by the
    # portal's verification view instead.
    verification = (
        '<b>Electronically Signed</b><br/>'
        f'<font size="7" color="#64748B">Signature: {signature_algorithm or "not signed"}<br/>'
        f'Key protection: {kem_algorithm or "—"}<br/>'
        f'Report No: {report_no}<br/>'
        'Integrity of this document (SHA-256 digest and<br/>'
        'post-quantum signature) is verifiable in the<br/>'
        'QuantumCare portal under this report number.</font>'
    )
    sig_rows = [[
        Paragraph(
            f'<b>{technician.get("full_name", "—")}</b><br/>'
            f'<font size="7.5" color="#64748B">{technician.get("user_id", "")}<br/>'
            f'Medical Laboratory Technologist<br/>Performed &amp; Verified By</font>', s["cell"]),
        Paragraph(verification, s["cell"]),
    ]]
    sig = Table(sig_rows, colWidths=[88 * mm, 90 * mm], hAlign="LEFT")
    sig.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LINEAFTER", (0, 0), (0, 0), 0.6, RULE),
        ("BACKGROUND", (1, 0), (1, 0), BAND),
    ]))
    flow.append(KeepTogether([Spacer(1, 2 * mm), sig]))

    flow.append(Spacer(1, 4 * mm))
    flow.append(Paragraph("— END OF REPORT —", ParagraphStyle(
        "end", parent=s["small"], alignment=TA_CENTER, fontName="Helvetica-Bold")))

    doc.build(flow, canvasmaker=lambda *a, **kw: _Canvas(*a, header_data=header_data, **kw))
    return buf.getvalue()
