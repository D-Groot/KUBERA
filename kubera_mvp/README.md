# KUBERA — MVP

**Knowledge-based · Uncertainty & Banking Evaluator for Risk Assessment**
*"Before AI acts, KUBERA checks."*

A working, end-to-end proof of concept for an AI decision-assurance layer
that sits between a bank's existing AI recommendation and the final action.
This is a real running application (Flask + Python), not a clickable mockup.

## What's actually implemented (not just described)

| Capability | Status | Where |
|---|---|---|
| **Input Integrity** — Error Level Analysis (ELA) + EXIF/metadata inspection on uploaded documents | ✅ Working | `app/core/integrity.py` |
| **Decision Stability (Probe Test)** — re-runs a bank-AI stand-in on a perturbed input and compares decisions | ✅ Working | `app/core/stability.py` |
| **Evidence retrieval** — tag-overlap matching against a policy-clause library and a historical-case library | ✅ Working (rule-based, not RAG/LLM) | `app/core/evidence.py` |
| **Unified Trust Score** — explicit weighted combination + routing (PROCEED / MONITOR / HUMAN_REVIEW) | ✅ Working | `app/core/trust.py` |
| **Decision Console UI** — upload a case, see the score breakdown, the flagged document region, the probe result, the evidence, and case history | ✅ Working | `app/templates/*`, SQLite-backed |
| Live bank-model API integration | 🔜 Next | — |
| Full automated triage | 🔜 Next | — |
| Adversarial red-teaming | 🔜 Next | — |
| Self-recalibration at scale | 🔜 Next | — |

The "bank AI" itself (`bank_ai_decision()` in `stability.py`) is an explicit,
deterministic stand-in for a real bank's model — swapping it for a live model
API call is exactly the "Next" item above. KUBERA's job is what surrounds
that box, not the box itself.

## Tech stack

- **Backend**: Python 3, Flask
- **Document integrity**: Pillow (JPEG re-encode diffing for ELA), NumPy (tile scoring)
- **Storage**: SQLite (zero-setup, swappable for Postgres later)
- **Frontend**: Server-rendered Jinja2 templates + hand-written CSS (dark navy/teal, matches the pitch deck)
- No JS framework, no external services required — runs fully offline.

## Run it

```bash
cd kubera_mvp
pip install -r requirements.txt   # Flask, Pillow, numpy, scikit-learn
python scripts/generate_sample_docs.py   # creates sample_docs/genuine_payslip.jpg and tampered_payslip.jpg
python run.py
```

Open http://localhost:5000, click **+ New Case**, upload
`sample_docs/genuine_payslip.jpg` or `sample_docs/tampered_payslip.jpg`,
fill in the loan fields (defaults are fine), and submit.

Observed results on the bundled sample pair:

| Document | Input Integrity | Trust Score | Route |
|---|---|---|---|
| `genuine_payslip.jpg` | ~0.82 | ~94/100 | PROCEED |
| `tampered_payslip.jpg` (edited net-salary field) | ~0.29 | ~66/100 | MONITOR |

(Exact numbers vary slightly with the loan inputs you enter, since Trust
Score also folds in affordability and evidence consistency.)

## How each pillar actually works

**1. Input Integrity.** The uploaded image is re-saved as a JPEG at a fixed
quality and diffed against the original (Error Level Analysis). A document
that was generated once has a fairly uniform diff response across the page;
a document where one field was edited and the image re-saved shows a
strongly anomalous diff localized to that field. We tile the diff map,
z-score each tile against the page's own noise floor, and flag tiles whose
peak anomaly clears a threshold. EXIF metadata (editor software tags,
inconsistent timestamps) is checked as a secondary, corroborating signal.

**2. Decision Stability (the Probe Test).** We take the case's features,
run them through the bank-AI stand-in, apply one small (3–6%) realistic
perturbation to a non-decisive field (self-reported monthly expenses), and
re-run the same model. If the decision flips, or confidence swings hard,
the case is flagged as unstable — independent of how confident it looked
originally. In production, probing would be triggered selectively on
uncertain/high-impact cases to control latency, not run on every case.

**3. Evidence.** A tag-overlap retrieval (not RAG/LLM — this POC doesn't
claim that) surfaces the most relevant policy clause and the most similar
historical case, from small JSON libraries in `data/`. This is the
reasoning trail a human reviewer sees, so no case is escalated on a bare
number alone.

**4. Unified Trust Score.** `0.35×Integrity + 0.35×Stability + 0.15×PolicyAlignment + 0.15×EvidenceConsistency`,
scaled to 0–100, thresholded into PROCEED (≥75) / MONITOR (≥45) / HUMAN_REVIEW (<45).
Weights and thresholds are plain constants in `app/core/trust.py` — easy to
defend and to tune.

## Honesty notes (what this MVP does *not* claim)

- Operates on image documents (JPEG/PNG); does not parse PDFs or run OCR.
- The "bank AI" is a deterministic stand-in, not a live model integration.
- Evidence retrieval is tag-based, not a trained retrieval or LLM system.
- The reviewer "Escalate" button is present but not wired to a queue — the
  Decision Console is the intended product surface, demonstrated end-to-end
  on synthetic data, not a claim of a deployed reviewer workflow.
- The 4/5 tampered-document detection rate referenced in the deck is from a
  small internal test sample, not a production benchmark.

## Project layout

```
kubera_mvp/
  app/
    core/
      integrity.py   # ELA + metadata → Input Integrity score
      stability.py   # bank-AI stand-in + Probe Test → Stability score
      evidence.py    # tag-overlap retrieval over policies/cases
      trust.py       # weighted combination → Trust Score + route
    templates/        # Decision Console UI (Jinja2)
    static/style.css  # dark navy/teal visual identity
    routes.py         # Flask views: upload, analyze, case detail, JSON API
  data/
    policies/policies.json
    cases/cases.json
  sample_docs/        # generated by scripts/generate_sample_docs.py
  scripts/generate_sample_docs.py
  run.py
  requirements.txt
```
