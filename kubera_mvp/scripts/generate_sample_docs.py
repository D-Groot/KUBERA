"""
Generates two demo documents so the pipeline can be exercised end-to-end
without needing a real payslip:
  - sample_docs/genuine_payslip.jpg   (single JPEG generation)
  - sample_docs/tampered_payslip.jpg  (net-salary field edited + recompressed,
                                        simulating a doubly-compressed edit)

This mirrors the POC described in the deck: genuine vs tampered salary slip,
tested with ELA + metadata inspection.
"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_docs")
os.makedirs(OUT_DIR, exist_ok=True)

W, H = 900, 500


def draw_payslip(net_salary: str):
    img = Image.new("RGB", (W, H), (250, 250, 248))
    d = ImageDraw.Draw(img)
    try:
        font_h = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        font_b = ImageFont.truetype("DejaVuSans.ttf", 18)
    except Exception:
        font_h = ImageFont.load_default()
        font_b = ImageFont.load_default()

    d.text((40, 30), "ACME BANK — SALARY SLIP", font=font_h, fill=(20, 20, 20))
    d.line((40, 75, 860, 75), fill=(180, 180, 180), width=2)

    rows = [
        ("Employee Name", "Rahul Verma"),
        ("Employee ID", "EMP-40217"),
        ("Pay Period", "August 2026"),
        ("Basic Pay", "42,000"),
        ("HRA", "12,000"),
        ("Other Allowances", "8,500"),
        ("Deductions", "-6,200"),
    ]
    y = 110
    for label, val in rows:
        d.text((60, y), label, font=font_b, fill=(60, 60, 60))
        d.text((500, y), val, font=font_b, fill=(20, 20, 20))
        y += 40

    d.line((40, y + 10, 860, y + 10), fill=(180, 180, 180), width=2)
    d.text((60, y + 30), "NET SALARY", font=font_h, fill=(20, 20, 20))
    d.text((500, y + 28), net_salary, font=font_h, fill=(20, 90, 40))

    d.text((60, H - 50), "This is a synthetically generated sample document for demo purposes only.",
           font=font_b, fill=(150, 150, 150))
    return img


def make_genuine():
    img = draw_payslip("56,300")
    path = os.path.join(OUT_DIR, "genuine_payslip.jpg")
    img.save(path, "JPEG", quality=92)
    return path


def make_tampered():
    """Simulate tampering: render the base doc, save once (as if the original
    was scanned/exported), then paste an edited NET SALARY figure and
    re-save — introducing a real, localized double-compression artifact
    that ELA can detect."""
    base = draw_payslip("56,300")
    stage1 = os.path.join(OUT_DIR, "_stage1.jpg")
    base.save(stage1, "JPEG", quality=90)

    img = Image.open(stage1).convert("RGB")
    d = ImageDraw.Draw(img)
    try:
        font_h = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    except Exception:
        font_h = ImageFont.load_default()

    # blank out and overwrite the net salary figure — the classic "edited field"
    d.rectangle((495, 385, 700, 420), fill=(250, 250, 248))
    d.text((500, 385), "96,300", font=font_h, fill=(20, 90, 40))

    path = os.path.join(OUT_DIR, "tampered_payslip.jpg")
    img.save(path, "JPEG", quality=90)
    os.remove(stage1)
    return path


if __name__ == "__main__":
    g = make_genuine()
    t = make_tampered()
    print("Genuine :", g)
    print("Tampered:", t)
