"""
Catalogue of laboratory report panels for QuantumCare.

This module is the single source of truth for what a given investigation
contains: its analytes, units, biological reference intervals and the layout
its report should be rendered with. The lab technician's data-entry form
(frontend), the validation on submission (API) and the printed PDF
(report_pdf.py) are all driven from here, so a panel can never disagree with
itself across those three surfaces.

Reference intervals were taken from published clinical sources rather than
invented; each panel carries the citation it was built from in ``source``.
They remain method- and population-dependent, which is why every printed
report also states the interval next to the result, exactly as a real
laboratory report does.

Layouts
-------
``tabular``   Analyte panels printed as
              Investigation | Result | Unit | Biological Reference Interval
``narrative`` Structured prose reports (ECG, radiology) printed as headed
              sections following the ACR/ESR ordering.
"""

from typing import Any, Optional

# Sex keys used by reference intervals. "A" = applies to all patients.
SEX_MALE = "M"
SEX_FEMALE = "F"
SEX_ANY = "A"


def _num(key: str, name: str, unit: str, ref: dict[str, Any], **kw) -> dict[str, Any]:
    """A numeric analyte row. ``ref`` maps a sex key to (low, high, display)."""
    return {
        "key": key,
        "name": name,
        "unit": unit,
        "input": "number",
        "step": kw.get("step", "0.01"),
        "ref": ref,
        "indent": kw.get("indent", False),
        "computed": kw.get("computed"),
        "note": kw.get("note"),
    }


def _text(key: str, name: str, **kw) -> dict[str, Any]:
    """A free-text or option analyte row (qualitative results)."""
    return {
        "key": key,
        "name": name,
        "unit": kw.get("unit", ""),
        "input": kw.get("input", "text"),
        "options": kw.get("options"),
        "ref": kw.get("ref", {SEX_ANY: (None, None, kw.get("expected", ""))}),
        "indent": kw.get("indent", False),
        "default": kw.get("default"),
        "note": kw.get("note"),
    }


def _field(key: str, label: str, input_type: str = "textarea", **kw) -> dict[str, Any]:
    """A narrative-report field (radiology / ECG prose sections)."""
    return {
        "key": key,
        "label": label,
        "input": input_type,
        "options": kw.get("options"),
        "placeholder": kw.get("placeholder", ""),
        "required": kw.get("required", False),
        "rows": kw.get("rows", 4),
        "unit": kw.get("unit", ""),
        "ref_text": kw.get("ref_text", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Haematology
# ─────────────────────────────────────────────────────────────────────────────

CBC = {
    "code": "CBC",
    "name": "Complete Blood Count (CBC) with Differential",
    "short_name": "Complete Blood Count",
    "category": "Haematology",
    "db_report_type": "CBC",
    "specimen": "Whole Blood (K2-EDTA)",
    "method": "Automated Haematology Analyser with Microscopic Review",
    "layout": "tabular",
    "source": "StatPearls, Normal and Abnormal Complete Blood Count With Differential (NCBI NBK604207)",
    "sections": [
        {
            "title": "Red Blood Cell Parameters",
            "analytes": [
                _num("hemoglobin", "Haemoglobin (Hb)", "g/dL",
                     {SEX_MALE: (13.0, 18.0, "13.0 – 18.0"), SEX_FEMALE: (12.0, 16.0, "12.0 – 16.0")}, step="0.1"),
                _num("rbc_count", "Total RBC Count", "million/µL",
                     {SEX_MALE: (4.6, 6.2, "4.6 – 6.2"), SEX_FEMALE: (4.2, 5.4, "4.2 – 5.4")}, step="0.01"),
                _num("hematocrit", "Haematocrit (PCV)", "%",
                     {SEX_MALE: (40.0, 54.0, "40 – 54"), SEX_FEMALE: (36.0, 48.0, "36 – 48")}, step="0.1"),
                _num("mcv", "Mean Corpuscular Volume (MCV)", "fL",
                     {SEX_ANY: (80.0, 100.0, "80 – 100")}, step="0.1"),
                _num("mch", "Mean Corpuscular Haemoglobin (MCH)", "pg",
                     {SEX_ANY: (27.0, 32.0, "27 – 32")}, step="0.1"),
                _num("mchc", "Mean Corpuscular Hb Concentration (MCHC)", "g/dL",
                     {SEX_ANY: (32.0, 36.0, "32 – 36")}, step="0.1"),
                _num("rdw", "Red Cell Distribution Width (RDW-CV)", "%",
                     {SEX_ANY: (11.5, 15.0, "11.5 – 15.0")}, step="0.1"),
            ],
        },
        {
            "title": "White Blood Cell Parameters",
            "analytes": [
                _num("wbc_count", "Total WBC Count (TLC)", "cells/µL",
                     {SEX_ANY: (4500, 11000, "4,500 – 11,000")}, step="1"),
            ],
        },
        {
            "title": "Differential Leucocyte Count (DLC)",
            "analytes": [
                _num("neutrophils_pct", "Neutrophils", "%",
                     {SEX_ANY: (40.0, 60.0, "40 – 60")}, step="0.1", indent=True),
                _num("lymphocytes_pct", "Lymphocytes", "%",
                     {SEX_ANY: (20.0, 40.0, "20 – 40")}, step="0.1", indent=True),
                _num("monocytes_pct", "Monocytes", "%",
                     {SEX_ANY: (2.0, 8.0, "2 – 8")}, step="0.1", indent=True),
                _num("eosinophils_pct", "Eosinophils", "%",
                     {SEX_ANY: (0.0, 4.0, "0 – 4")}, step="0.1", indent=True),
                _num("basophils_pct", "Basophils", "%",
                     {SEX_ANY: (0.0, 1.0, "0 – 1")}, step="0.1", indent=True),
            ],
        },
        {
            "title": "Absolute Leucocyte Counts",
            "analytes": [
                _num("anc", "Absolute Neutrophil Count", "cells/µL",
                     {SEX_ANY: (1500, 8000, "1,500 – 8,000")}, step="1", indent=True),
                _num("alc", "Absolute Lymphocyte Count", "cells/µL",
                     {SEX_ANY: (1000, 4000, "1,000 – 4,000")}, step="1", indent=True),
                _num("amc", "Absolute Monocyte Count", "cells/µL",
                     {SEX_ANY: (200, 1000, "200 – 1,000")}, step="1", indent=True),
                _num("aec", "Absolute Eosinophil Count", "cells/µL",
                     {SEX_ANY: (0, 500, "0 – 500")}, step="1", indent=True),
            ],
        },
        {
            "title": "Platelet Parameters",
            "analytes": [
                _num("platelet_count", "Platelet Count", "cells/µL",
                     {SEX_ANY: (150000, 400000, "150,000 – 400,000")}, step="1000"),
                _num("mpv", "Mean Platelet Volume (MPV)", "fL",
                     {SEX_ANY: (7.5, 11.5, "7.5 – 11.5")}, step="0.1"),
            ],
        },
        {
            "title": "Peripheral Smear Examination",
            "analytes": [
                _text("rbc_morphology", "RBC Morphology", input="select", expected="Normocytic Normochromic",
                      options=["Normocytic Normochromic", "Microcytic Hypochromic", "Macrocytic",
                               "Dimorphic", "Normocytic Hypochromic"], default="Normocytic Normochromic"),
                _text("wbc_morphology", "WBC Morphology", input="select", expected="Within Normal Limits",
                      options=["Within Normal Limits", "Toxic Granulation", "Left Shift", "Atypical Lymphocytes"],
                      default="Within Normal Limits"),
                _text("platelet_morphology", "Platelets on Smear", input="select", expected="Adequate",
                      options=["Adequate", "Reduced", "Increased", "Clumped"], default="Adequate"),
                _text("hemoparasites", "Haemoparasites", input="select", expected="Not Detected",
                      options=["Not Detected", "Plasmodium vivax", "Plasmodium falciparum", "Microfilaria"],
                      default="Not Detected"),
            ],
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Clinical Biochemistry
# ─────────────────────────────────────────────────────────────────────────────

BLOOD_SUGAR = {
    "code": "BLOOD_SUGAR",
    "name": "Blood Glucose Studies",
    "short_name": "Blood Sugar",
    "category": "Clinical Biochemistry",
    "db_report_type": "Blood Sugar",
    "specimen": "Plasma (Sodium Fluoride) / Whole Blood (EDTA) for HbA1c",
    "method": "Hexokinase / GOD-POD; HbA1c by HPLC (NGSP certified)",
    "layout": "tabular",
    "source": "American Diabetes Association, Standards of Care — Classification and Diagnosis of Diabetes",
    "sections": [
        {
            "title": "Glucose Estimation",
            "analytes": [
                _num("fbs", "Fasting Blood Sugar (FBS)", "mg/dL",
                     {SEX_ANY: (70.0, 99.0, "70 – 99")}, step="0.1",
                     note="ADA: 100–125 impaired fasting glucose; ≥126 diabetes"),
                _num("ppbs", "Post-Prandial Blood Sugar (2 hr PPBS)", "mg/dL",
                     {SEX_ANY: (70.0, 139.0, "< 140")}, step="0.1",
                     note="ADA: 140–199 impaired glucose tolerance; ≥200 diabetes"),
                _num("rbs", "Random Blood Sugar (RBS)", "mg/dL",
                     {SEX_ANY: (70.0, 139.0, "< 140")}, step="0.1",
                     note="ADA: ≥200 with classic symptoms is diagnostic of diabetes"),
            ],
        },
        {
            "title": "Glycaemic Control",
            "analytes": [
                _num("hba1c", "Glycated Haemoglobin (HbA1c)", "%",
                     {SEX_ANY: (4.0, 5.6, "< 5.7")}, step="0.1",
                     note="ADA: 5.7–6.4 prediabetes; ≥6.5 diabetes"),
                _num("eag", "Estimated Average Glucose (eAG)", "mg/dL",
                     {SEX_ANY: (70.0, 114.0, "< 117")}, step="1", computed="eag"),
            ],
        },
    ],
}


LFT = {
    "code": "LFT",
    "name": "Liver Function Test (LFT)",
    "short_name": "Liver Function Test",
    "category": "Clinical Biochemistry",
    "db_report_type": "Liver Function",
    "specimen": "Serum (Plain / SST)",
    "method": "Spectrophotometry — IFCC / Diazo / BCG",
    "layout": "tabular",
    "source": "Cleveland Clinic Liver Function Tests reference values (via labtestsguide.com LFT panel)",
    "sections": [
        {
            "title": "Bilirubin Studies",
            "analytes": [
                _num("bilirubin_total", "Bilirubin — Total", "mg/dL",
                     {SEX_ANY: (0.1, 1.2, "0.1 – 1.2")}, step="0.01"),
                _num("bilirubin_direct", "Bilirubin — Direct (Conjugated)", "mg/dL",
                     {SEX_ANY: (0.0, 0.3, "0.0 – 0.3")}, step="0.01", indent=True),
                _num("bilirubin_indirect", "Bilirubin — Indirect (Unconjugated)", "mg/dL",
                     {SEX_ANY: (0.1, 0.9, "0.1 – 0.9")}, step="0.01", indent=True,
                     computed="bilirubin_indirect"),
            ],
        },
        {
            "title": "Liver Enzymes",
            "analytes": [
                _num("sgpt", "Alanine Transaminase (SGPT / ALT)", "U/L",
                     {SEX_ANY: (7.0, 56.0, "7 – 56")}, step="0.1"),
                _num("sgot", "Aspartate Transaminase (SGOT / AST)", "U/L",
                     {SEX_ANY: (10.0, 40.0, "10 – 40")}, step="0.1"),
                _num("alp", "Alkaline Phosphatase (ALP)", "U/L",
                     {SEX_ANY: (44.0, 147.0, "44 – 147")}, step="0.1"),
                _num("ggt", "Gamma Glutamyl Transferase (GGT)", "U/L",
                     {SEX_ANY: (9.0, 48.0, "9 – 48")}, step="0.1"),
            ],
        },
        {
            "title": "Protein Studies",
            "analytes": [
                _num("total_protein", "Total Protein", "g/dL",
                     {SEX_ANY: (6.0, 8.3, "6.0 – 8.3")}, step="0.1"),
                _num("albumin", "Albumin", "g/dL",
                     {SEX_ANY: (3.5, 5.0, "3.5 – 5.0")}, step="0.1"),
                _num("globulin", "Globulin", "g/dL",
                     {SEX_ANY: (2.0, 3.5, "2.0 – 3.5")}, step="0.1", computed="globulin"),
                _num("ag_ratio", "Albumin / Globulin Ratio", "",
                     {SEX_ANY: (1.0, 2.1, "1.0 – 2.1")}, step="0.01", computed="ag_ratio"),
            ],
        },
    ],
}


KFT = {
    "code": "KFT",
    "name": "Renal Function Test (RFT / KFT)",
    "short_name": "Kidney Function Test",
    "category": "Clinical Biochemistry",
    "db_report_type": "Kidney Function",
    "specimen": "Serum (Plain / SST)",
    "method": "Spectrophotometry — Urease / Jaffe (IDMS traceable)",
    "layout": "tabular",
    "source": "KDIGO CKD guideline (eGFR staging) with standard serum chemistry intervals",
    "sections": [
        {
            "title": "Renal Parameters",
            "analytes": [
                _num("urea", "Blood Urea", "mg/dL", {SEX_ANY: (17.0, 43.0, "17 – 43")}, step="0.1"),
                _num("bun", "Blood Urea Nitrogen (BUN)", "mg/dL",
                     {SEX_ANY: (8.0, 20.0, "8 – 20")}, step="0.1", computed="bun"),
                _num("creatinine", "Serum Creatinine", "mg/dL",
                     {SEX_MALE: (0.7, 1.3, "0.7 – 1.3"), SEX_FEMALE: (0.6, 1.1, "0.6 – 1.1")}, step="0.01"),
                _num("egfr", "Estimated GFR (CKD-EPI 2021)", "mL/min/1.73m²",
                     {SEX_ANY: (90.0, 200.0, "≥ 90")}, step="0.1",
                     note="KDIGO: 60–89 mildly decreased; 30–59 moderate; <30 severe"),
                _num("uric_acid", "Serum Uric Acid", "mg/dL",
                     {SEX_MALE: (3.4, 7.0, "3.4 – 7.0"), SEX_FEMALE: (2.4, 6.0, "2.4 – 6.0")}, step="0.1"),
            ],
        },
        {
            "title": "Electrolytes",
            "analytes": [
                _num("sodium", "Sodium (Na⁺)", "mmol/L", {SEX_ANY: (136.0, 145.0, "136 – 145")}, step="0.1"),
                _num("potassium", "Potassium (K⁺)", "mmol/L", {SEX_ANY: (3.5, 5.1, "3.5 – 5.1")}, step="0.1"),
                _num("chloride", "Chloride (Cl⁻)", "mmol/L", {SEX_ANY: (98.0, 107.0, "98 – 107")}, step="0.1"),
                _num("calcium", "Calcium (Total)", "mg/dL", {SEX_ANY: (8.6, 10.2, "8.6 – 10.2")}, step="0.1"),
                _num("phosphorus", "Phosphorus", "mg/dL", {SEX_ANY: (2.5, 4.5, "2.5 – 4.5")}, step="0.1"),
            ],
        },
    ],
}


LIPID = {
    "code": "LIPID",
    "name": "Lipid Profile",
    "short_name": "Lipid Profile",
    "category": "Clinical Biochemistry",
    "db_report_type": "Lipid Profile",
    "specimen": "Serum (Plain / SST) — 9 to 12 hour fasting",
    "method": "Enzymatic Colorimetry (CHOD-PAP / GPO-PAP)",
    "layout": "tabular",
    "source": "NCEP ATP III / ACC-AHA desirable lipid levels",
    "sections": [
        {
            "title": "Lipid Parameters",
            "analytes": [
                _num("total_cholesterol", "Total Cholesterol", "mg/dL",
                     {SEX_ANY: (0.0, 199.0, "< 200 Desirable")}, step="0.1",
                     note="200–239 borderline high; ≥240 high"),
                _num("triglycerides", "Triglycerides", "mg/dL",
                     {SEX_ANY: (0.0, 149.0, "< 150 Normal")}, step="0.1",
                     note="150–199 borderline high; 200–499 high"),
                _num("hdl", "HDL Cholesterol", "mg/dL",
                     {SEX_MALE: (40.0, 200.0, "> 40"), SEX_FEMALE: (50.0, 200.0, "> 50")}, step="0.1"),
                _num("ldl", "LDL Cholesterol", "mg/dL",
                     {SEX_ANY: (0.0, 99.0, "< 100 Optimal")}, step="0.1", computed="ldl",
                     note="100–129 near optimal; 130–159 borderline high"),
                _num("vldl", "VLDL Cholesterol", "mg/dL",
                     {SEX_ANY: (5.0, 30.0, "5 – 30")}, step="0.1", computed="vldl"),
                _num("chol_hdl_ratio", "Total Cholesterol / HDL Ratio", "",
                     {SEX_ANY: (0.0, 4.5, "< 4.5")}, step="0.01", computed="chol_hdl_ratio"),
            ],
        },
    ],
}


THYROID = {
    "code": "THYROID",
    "name": "Thyroid Profile (T3, T4, TSH)",
    "short_name": "Thyroid Profile",
    "category": "Immunoassay",
    "db_report_type": "Other",
    "specimen": "Serum (Plain / SST)",
    "method": "Chemiluminescent Immunoassay (CLIA)",
    "layout": "tabular",
    "source": "Standard adult thyroid function reference intervals (CLIA platform)",
    "sections": [
        {
            "title": "Thyroid Parameters",
            "analytes": [
                _num("t3", "Tri-iodothyronine (Total T3)", "ng/dL",
                     {SEX_ANY: (80.0, 200.0, "80 – 200")}, step="0.1"),
                _num("t4", "Thyroxine (Total T4)", "µg/dL",
                     {SEX_ANY: (5.1, 14.1, "5.1 – 14.1")}, step="0.1"),
                _num("tsh", "Thyroid Stimulating Hormone (TSH)", "µIU/mL",
                     {SEX_ANY: (0.4, 4.0, "0.40 – 4.00")}, step="0.01",
                     note="Pregnancy and age-specific intervals differ"),
            ],
        },
    ],
}


URINE = {
    "code": "URINE",
    "name": "Urine Routine & Microscopy Examination",
    "short_name": "Urine Analysis",
    "category": "Clinical Pathology",
    "db_report_type": "Urine Test",
    "specimen": "Random Midstream Urine",
    "method": "Dipstick Reflectance Photometry with Manual Microscopy",
    "layout": "tabular",
    "source": "Medscape Urinalysis reference ranges; standard urine routine report format",
    "sections": [
        {
            "title": "Physical Examination",
            "analytes": [
                _text("colour", "Colour", input="select", expected="Pale Yellow",
                      options=["Pale Yellow", "Straw", "Dark Yellow", "Amber", "Reddish", "Colourless"],
                      default="Pale Yellow"),
                _text("appearance", "Appearance", input="select", expected="Clear",
                      options=["Clear", "Slightly Turbid", "Turbid"], default="Clear"),
                _num("volume", "Volume", "mL", {SEX_ANY: (None, None, "—")}, step="1"),
                _num("specific_gravity", "Specific Gravity", "",
                     {SEX_ANY: (1.005, 1.030, "1.005 – 1.030")}, step="0.001"),
                _num("ph", "Reaction (pH)", "", {SEX_ANY: (4.6, 8.0, "4.6 – 8.0")}, step="0.1"),
            ],
        },
        {
            "title": "Chemical Examination",
            "analytes": [
                _text("protein", "Protein (Albumin)", input="select", expected="Negative",
                      options=["Negative", "Trace", "1+", "2+", "3+", "4+"], default="Negative"),
                _text("glucose", "Glucose", input="select", expected="Negative",
                      options=["Negative", "Trace", "1+", "2+", "3+", "4+"], default="Negative"),
                _text("ketones", "Ketone Bodies", input="select", expected="Negative",
                      options=["Negative", "Trace", "1+", "2+", "3+"], default="Negative"),
                _text("bilirubin", "Bilirubin", input="select", expected="Negative",
                      options=["Negative", "1+", "2+", "3+"], default="Negative"),
                _text("urobilinogen", "Urobilinogen", input="select", expected="Normal",
                      options=["Normal", "Increased"], default="Normal"),
                _text("nitrite", "Nitrite", input="select", expected="Negative",
                      options=["Negative", "Positive"], default="Negative"),
                _text("blood", "Blood", input="select", expected="Negative",
                      options=["Negative", "Trace", "1+", "2+", "3+"], default="Negative"),
                _text("leukocyte_esterase", "Leucocyte Esterase", input="select", expected="Negative",
                      options=["Negative", "Trace", "1+", "2+", "3+"], default="Negative"),
            ],
        },
        {
            "title": "Microscopic Examination",
            "analytes": [
                _num("pus_cells", "Pus Cells (WBC)", "/HPF", {SEX_ANY: (0, 5, "0 – 5")}, step="1"),
                _num("rbc_urine", "Red Blood Cells", "/HPF", {SEX_ANY: (0, 2, "0 – 2")}, step="1"),
                _num("epithelial_cells", "Epithelial Cells", "/HPF", {SEX_ANY: (0, 3, "0 – 3")}, step="1"),
                _text("casts", "Casts", input="select", expected="Nil",
                      options=["Nil", "Hyaline", "Granular", "Cellular", "Epithelial", "RBC Casts"],
                      default="Nil"),
                _text("crystals", "Crystals", input="select", expected="Nil",
                      options=["Nil", "Calcium Oxalate", "Uric Acid", "Triple Phosphate", "Amorphous Urates"],
                      default="Nil"),
                _text("bacteria", "Bacteria", input="select", expected="Nil",
                      options=["Nil", "Occasional", "Few", "Moderate", "Numerous"], default="Nil"),
                _text("yeast_cells", "Yeast Cells", input="select", expected="Nil",
                      options=["Nil", "Present"], default="Nil"),
                _text("mucus", "Mucus Threads", input="select", expected="Nil",
                      options=["Nil", "Present"], default="Nil"),
            ],
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Narrative reports
# ─────────────────────────────────────────────────────────────────────────────

ECG = {
    "code": "ECG",
    "name": "Electrocardiogram (12-Lead ECG)",
    "short_name": "ECG",
    "category": "Cardiology",
    "db_report_type": "ECG",
    "specimen": "12-Lead Surface Electrocardiogram",
    "method": "Standard 12-Lead ECG, 25 mm/s, 10 mm/mV",
    "layout": "narrative",
    "source": "ECGwaves / Medscape normal ECG interval reference values",
    "measurements": [
        _num("heart_rate", "Heart Rate", "bpm", {SEX_ANY: (50, 100, "50 – 100")}, step="1"),
        _num("pr_interval", "PR Interval", "ms", {SEX_ANY: (120, 200, "120 – 200")}, step="1"),
        _num("qrs_duration", "QRS Duration", "ms", {SEX_ANY: (70, 110, "70 – 110")}, step="1"),
        _num("qt_interval", "QT Interval", "ms", {SEX_ANY: (350, 440, "350 – 440")}, step="1"),
        _num("qtc_interval", "QTc (Bazett)", "ms",
             {SEX_MALE: (350, 450, "< 450"), SEX_FEMALE: (350, 460, "< 460")}, step="1"),
        _num("qrs_axis", "QRS Axis", "degrees", {SEX_ANY: (-30, 90, "-30° to +90°")}, step="1"),
    ],
    "sections": [
        {
            "title": "Clinical Details",
            "fields": [
                _field("clinical_indication", "Clinical Indication", "textarea", rows=2, required=True,
                       placeholder="e.g. Chest pain, palpitations, pre-operative evaluation"),
            ],
        },
        {
            "title": "Interpretation",
            "fields": [
                _field("rhythm", "Rhythm", "select", required=True,
                       options=["Normal Sinus Rhythm", "Sinus Bradycardia", "Sinus Tachycardia",
                                "Atrial Fibrillation", "Atrial Flutter", "Supraventricular Tachycardia",
                                "Ventricular Tachycardia", "Paced Rhythm", "Junctional Rhythm"]),
                _field("p_wave", "P Wave", "select",
                       options=["Normal", "Absent", "Peaked (P pulmonale)", "Broad/Notched (P mitrale)", "Inverted"]),
                _field("conduction", "AV / Intraventricular Conduction", "select",
                       options=["Normal", "First-degree AV block", "Second-degree AV block (Mobitz I)",
                                "Second-degree AV block (Mobitz II)", "Complete heart block",
                                "Right bundle branch block", "Left bundle branch block",
                                "Left anterior fascicular block"]),
                _field("st_t_changes", "ST Segment / T Wave", "select",
                       options=["Normal", "ST elevation", "ST depression", "T wave inversion",
                                "Non-specific ST-T changes", "Tall peaked T waves"]),
                _field("st_t_detail", "ST/T Distribution & Leads Involved", "textarea", rows=2,
                       placeholder="e.g. ST elevation 2 mm in leads II, III, aVF"),
                _field("other_findings", "Other Findings", "textarea", rows=3,
                       placeholder="e.g. Left ventricular hypertrophy by voltage criteria, poor R wave progression"),
            ],
        },
        {
            "title": "Conclusion",
            "fields": [
                _field("impression", "Impression", "textarea", rows=4, required=True,
                       placeholder="Summary conclusion of the ECG"),
                _field("recommendations", "Recommendation", "textarea", rows=2,
                       placeholder="e.g. Clinical correlation advised; cardiology consultation"),
            ],
        },
    ],
}


RADIOLOGY = {
    "code": "RADIOLOGY",
    "name": "Radiological Investigation Report",
    "short_name": "Radiology (X-Ray / MRI / CT / USG)",
    "category": "Radiology & Imaging",
    "db_report_type": "X-Ray",
    "specimen": "Diagnostic Imaging Study",
    "method": "Digital Radiography / MRI / CT / Ultrasonography",
    "layout": "narrative",
    "source": "ESR paper on structured reporting in radiology; ACR reporting sections "
              "(Exam, History, Technique, Comparison, Findings, Impression)",
    "sections": [
        {
            "title": "Examination",
            "fields": [
                _field("modality", "Modality", "select", required=True,
                       options=["X-Ray", "MRI", "CT Scan", "Ultrasound", "Mammography", "Fluoroscopy"]),
                _field("study_name", "Study / Region Examined", "text", required=True,
                       placeholder="e.g. Chest PA View / MRI Brain with Contrast"),
                _field("clinical_indication", "Clinical History & Indication", "textarea", rows=3, required=True,
                       placeholder="Reason for the examination"),
            ],
        },
        {
            "title": "Technique",
            "fields": [
                _field("technique", "Technique", "textarea", rows=3, required=True,
                       placeholder="e.g. Frontal PA projection of the chest obtained in full inspiration"),
                _field("contrast", "Contrast", "select",
                       options=["Not Administered", "Intravenous", "Oral", "Intravenous and Oral", "Intra-articular"]),
                _field("comparison", "Comparison", "text",
                       placeholder="e.g. Prior chest radiograph dated 12-Mar-2026, or 'None available'"),
            ],
        },
        {
            "title": "Findings",
            "fields": [
                _field("findings", "Findings", "textarea", rows=10, required=True,
                       placeholder="Systematic description of the imaging findings"),
            ],
        },
        {
            "title": "Impression",
            "fields": [
                _field("impression", "Impression", "textarea", rows=5, required=True,
                       placeholder="Numbered summary, most to least clinically significant"),
                _field("recommendations", "Recommendation", "textarea", rows=3,
                       placeholder="e.g. Follow-up imaging in 3 months; correlate clinically"),
            ],
        },
    ],
}


PANELS: dict[str, dict[str, Any]] = {
    p["code"]: p for p in (CBC, BLOOD_SUGAR, LFT, KFT, LIPID, THYROID, URINE, ECG, RADIOLOGY)
}


def get_panel(code: str) -> Optional[dict[str, Any]]:
    return PANELS.get((code or "").strip().upper())


def list_panels() -> list[dict[str, Any]]:
    """Catalogue summary used to populate the technician's panel picker."""
    return [
        {
            "code": p["code"],
            "name": p["name"],
            "short_name": p["short_name"],
            "category": p["category"],
            "layout": p["layout"],
            "specimen": p["specimen"],
        }
        for p in PANELS.values()
    ]


def analytes_of(panel: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every analyte of a tabular panel, in print order."""
    out: list[dict[str, Any]] = []
    for section in panel.get("sections", []):
        out.extend(section.get("analytes", []))
    return out


def resolve_ref(analyte: dict[str, Any], sex: str) -> tuple[Optional[float], Optional[float], str]:
    """Pick the reference interval that applies to this patient's sex."""
    ref = analyte.get("ref") or {}
    key = SEX_MALE if (sex or "").upper().startswith("M") else (
        SEX_FEMALE if (sex or "").upper().startswith("F") else SEX_ANY
    )
    entry = ref.get(key) or ref.get(SEX_ANY) or (None, None, "")
    low, high, display = entry
    return low, high, display


def flag_for(value: Any, low: Optional[float], high: Optional[float]) -> str:
    """Return 'H', 'L' or '' for a numeric result against its interval."""
    if low is None and high is None:
        return ""
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return ""
    if high is not None and numeric > high:
        return "H"
    if low is not None and numeric < low:
        return "L"
    return ""


def _f(values: dict[str, Any], key: str) -> Optional[float]:
    try:
        raw = values.get(key)
        if raw is None or str(raw).strip() == "":
            return None
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def apply_computed(panel_code: str, values: dict[str, Any]) -> dict[str, Any]:
    """
    Derive the values a real analyser reports as calculated rather than measured.

    Only fills a field when the technician left it blank, so an explicitly
    entered value always wins.
    """
    v = dict(values)

    def put(key: str, result: Optional[float], digits: int = 2):
        if result is None:
            return
        if str(v.get(key, "")).strip() == "":
            v[key] = round(result, digits)

    code = (panel_code or "").upper()

    if code == "LFT":
        total, direct = _f(v, "bilirubin_total"), _f(v, "bilirubin_direct")
        if total is not None and direct is not None:
            put("bilirubin_indirect", total - direct)
        protein, albumin = _f(v, "total_protein"), _f(v, "albumin")
        if protein is not None and albumin is not None:
            put("globulin", protein - albumin)
        globulin = _f(v, "globulin")
        if albumin is not None and globulin:
            put("ag_ratio", albumin / globulin)

    elif code == "LIPID":
        total, hdl, tg = _f(v, "total_cholesterol"), _f(v, "hdl"), _f(v, "triglycerides")
        if tg is not None:
            put("vldl", tg / 5.0, 1)
        vldl = _f(v, "vldl")
        # Friedewald estimation is not valid once triglycerides exceed 400 mg/dL.
        if total is not None and hdl is not None and vldl is not None and (tg is None or tg <= 400):
            put("ldl", total - hdl - vldl, 1)
        if total is not None and hdl:
            put("chol_hdl_ratio", total / hdl)

    elif code == "KFT":
        urea = _f(v, "urea")
        if urea is not None:
            put("bun", urea * 0.467, 1)

    elif code == "BLOOD_SUGAR":
        hba1c = _f(v, "hba1c")
        if hba1c is not None:
            # ADAG study regression used by the ADA to report eAG alongside HbA1c.
            put("eag", (28.7 * hba1c) - 46.7, 0)

    return v


def interpretation_for(panel_code: str, values: dict[str, Any], sex: str) -> Optional[str]:
    """
    A short, guideline-anchored comment for panels where one is standard.

    Deliberately conservative: it states the classification a guideline gives
    to a value, and never suggests treatment.
    """
    code = (panel_code or "").upper()

    if code == "BLOOD_SUGAR":
        notes: list[str] = []
        fbs, ppbs, hba1c = _f(values, "fbs"), _f(values, "ppbs"), _f(values, "hba1c")
        if fbs is not None:
            if fbs >= 126:
                notes.append(f"Fasting glucose {fbs:g} mg/dL is in the diabetic range (ADA ≥126 mg/dL).")
            elif fbs >= 100:
                notes.append(f"Fasting glucose {fbs:g} mg/dL indicates impaired fasting glucose (ADA 100–125 mg/dL).")
        if ppbs is not None:
            if ppbs >= 200:
                notes.append(f"2-hour post-prandial glucose {ppbs:g} mg/dL is in the diabetic range (ADA ≥200 mg/dL).")
            elif ppbs >= 140:
                notes.append(f"2-hour post-prandial glucose {ppbs:g} mg/dL indicates impaired glucose tolerance (ADA 140–199 mg/dL).")
        if hba1c is not None:
            if hba1c >= 6.5:
                notes.append(f"HbA1c {hba1c:g}% meets the ADA diagnostic threshold for diabetes (≥6.5%).")
            elif hba1c >= 5.7:
                notes.append(f"HbA1c {hba1c:g}% is in the prediabetes range (ADA 5.7–6.4%).")
        if notes:
            notes.append("Diagnosis requires confirmation on a repeat sample unless the patient is symptomatic. Clinical correlation advised.")
            return " ".join(notes)
        return None

    if code == "LIPID":
        ldl, tg = _f(values, "ldl"), _f(values, "triglycerides")
        notes = []
        if ldl is not None and ldl >= 160:
            notes.append(f"LDL cholesterol {ldl:g} mg/dL is high (NCEP ATP III ≥160 mg/dL).")
        if tg is not None and tg > 400:
            notes.append("Triglycerides exceed 400 mg/dL; LDL by Friedewald estimation is unreliable and a direct LDL assay is advised.")
        return " ".join(notes) if notes else None

    if code == "KFT":
        egfr = _f(values, "egfr")
        if egfr is not None and egfr < 60:
            return (f"Estimated GFR {egfr:g} mL/min/1.73m² is below 60; per KDIGO this requires confirmation "
                    "over ≥3 months to establish chronic kidney disease. Clinical correlation advised.")
        return None

    return None
