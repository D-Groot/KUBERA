import json
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, jsonify

from . import get_db, UPLOAD_DIR
from .core.integrity import analyze_document
from .core.stability import run_probe_test
from .core.evidence import find_evidence
from .core.trust import compute_trust_score, compute_policy_alignment, compute_evidence_consistency

bp = Blueprint("kubera", __name__)

ALLOWED_EXT = {"png", "jpg", "jpeg"}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@bp.route("/")
def index():
    db = get_db()
    rows = db.execute(
        "SELECT id, created_at, trust_score, route FROM cases ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    return render_template("index.html", cases=rows)


@bp.route("/new", methods=["GET"])
def new_case():
    return render_template("new_case.html")


@bp.route("/analyze", methods=["POST"])
def analyze():
    # --- 1. Document (Input Integrity) ---
    file = request.files.get("document")
    if not file or file.filename == "" or not _allowed(file.filename):
        return render_template("new_case.html", error="Please upload a PNG/JPG document.")

    case_id = "KB-" + uuid.uuid4().hex[:6].upper()
    original_name = f"{case_id}_original.jpg"
    preview_name = f"{case_id}_ela.jpg"
    original_path = os.path.join(UPLOAD_DIR, original_name)
    preview_path = os.path.join(UPLOAD_DIR, preview_name)
    file.save(original_path)

    integrity = analyze_document(original_path, save_preview_to=preview_path)

    # --- 2. Loan features (Decision Stability probe) ---
    def f(name, default=0.0):
        try:
            return float(request.form.get(name, default))
        except (TypeError, ValueError):
            return default

    features = {
        "monthly_income": f("monthly_income", 60000),
        "monthly_expenses": f("monthly_expenses", 35000),
        "requested_amount": f("requested_amount", 500000),
        "credit_history_score": f("credit_history_score", 0.7),
        "employment_years": f("employment_years", 3),
    }
    stability = run_probe_test(features)

    # --- 3. Evidence retrieval ---
    query_tags = ["income_proof"]
    if integrity.integrity_score < 0.6:
        query_tags += ["document_integrity", "tampering"]
    if stability.flipped or stability.stability_score < 0.5:
        query_tags += ["decision_stability", "confidence"]
    affordability_ratio = (
        (features["monthly_income"] - features["monthly_expenses"])
        / max(features["requested_amount"], 1)
    ) * 100  # scaled so a "normal" ratio lands near ~1-3 for demo purposes
    query_tags += ["affordability", "income"]

    evidence = find_evidence(query_tags)

    # --- 4. Unified Trust Score ---
    policy_alignment = compute_policy_alignment(affordability_ratio)
    evidence_consistency = compute_evidence_consistency(evidence["similar_cases"])
    trust = compute_trust_score(
        integrity.integrity_score,
        stability.stability_score,
        policy_alignment,
        evidence_consistency,
    )

    payload = {
        "case_id": case_id,
        "features": features,
        "affordability_ratio": round(affordability_ratio, 2),
        "integrity": integrity.__dict__,
        "stability": {
            "stability_score": stability.stability_score,
            "original": stability.original,
            "perturbed": stability.perturbed,
            "perturbation": stability.perturbation,
            "flipped": stability.flipped,
            "note": stability.note,
        },
        "evidence": evidence,
        "trust": {"trust_score": trust.trust_score, "route": trust.route, "breakdown": trust.breakdown},
        "original_image": original_name,
        "ela_image": preview_name,
    }

    db = get_db()
    db.execute(
        """INSERT INTO cases
           (id, created_at, trust_score, route, integrity_score, stability_score,
            policy_alignment, evidence_consistency, payload_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            case_id,
            datetime.now(timezone.utc).isoformat(),
            trust.trust_score,
            trust.route,
            integrity.integrity_score,
            stability.stability_score,
            policy_alignment,
            evidence_consistency,
            json.dumps(payload),
        ),
    )
    db.commit()

    return redirect(url_for("kubera.case_detail", case_id=case_id))


@bp.route("/case/<case_id>")
def case_detail(case_id):
    db = get_db()
    row = db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        return "Case not found", 404
    payload = json.loads(row["payload_json"])
    return render_template("case_detail.html", case=payload, row=row)


@bp.route("/api/case/<case_id>")
def api_case(case_id):
    db = get_db()
    row = db.execute("SELECT payload_json FROM cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(json.loads(row["payload_json"]))
