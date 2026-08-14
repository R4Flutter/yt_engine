"""M3 thumbnail mining (PLAN.md Section 5, M3 step 6).

OpenCV + EasyOCR on outlier thumbnails (data/thumbs/<video_id>.<ext>):
  - word count (OCR, low-confidence tokens dropped)
  - contrast (gray std), saturation (HSV S mean), brightness (V mean)
  - face detection (Haar cascade)

Stores metrics into video_features, prints niche-level benchmarks.

Usage:
  python -m miner.thumbs               # full pass
  python -m miner.thumbs --no-ocr      # skip OCR (fast) — word_count stays NULL
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from config import ROOT, fix_console, load_settings, resolve_path
from db import get_connection

FACE_MODEL = ROOT / "models" / "face_detection_yunet.onnx"


def load_image(path: Path):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:  # some .webp need explicit decode
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return img


def _has_face(img) -> int:
    try:
        h, w = img.shape[:2]
        detector = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (w, h))
        _, faces = detector.detect(img)
        return int(faces is not None and len(faces) > 0)
    except Exception:
        return 0


def analyze(path: Path, ocr=None) -> dict:
    img = load_image(path)
    if img is None:
        return {}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    contrast = float(np.std(gray))
    saturation = float(np.mean(hsv[:, :, 1]))
    has_face = _has_face(img)
    words = None
    if ocr is not None:
        try:
            res = ocr.readtext(np.asarray(img))
            words = len([t for _, t, conf in res if conf > 0.5 and len(t.strip()) > 1])
        except Exception as e:
            print(f"  [thumbs] OCR failed on {path.name}: {e}", file=sys.stderr)
    return {"thumb_contrast": round(contrast, 2), "thumb_saturation": round(saturation, 2),
            "thumb_has_face": int(has_face), "thumb_word_count": words}


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-ocr", action="store_true", help="skip EasyOCR word count")
    args = ap.parse_args()
    settings = load_settings()
    conn = get_connection()
    thumbs_dir = resolve_path(settings["paths"]["thumbs"])
    thumbs = [p for p in thumbs_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    if not thumbs:
        print("[thumbs] no thumbnails — run deep_crawl first")
        return

    ocr = None
    if not args.no_ocr:
        try:
            import easyocr
            ocr = easyocr.Reader(["en"], gpu=False, verbose=False)
        except Exception as e:
            print(f"[thumbs] EasyOCR unavailable ({e}); word counts skipped", file=sys.stderr)

    done = 0
    for p in thumbs:
        video_id = p.stem
        if not conn.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,)).fetchone():
            continue
        m = analyze(p, ocr)
        if not m:
            print(f"  [thumbs] cannot decode {p.name}")
            continue
        conn.execute(
            """INSERT INTO video_features (video_id, thumb_contrast, thumb_saturation,
               thumb_has_face, thumb_word_count)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                 thumb_contrast=excluded.thumb_contrast,
                 thumb_saturation=excluded.thumb_saturation,
                 thumb_has_face=excluded.thumb_has_face,
                 thumb_word_count=excluded.thumb_word_count""",
            (video_id, m["thumb_contrast"], m["thumb_saturation"],
             m["thumb_has_face"], m["thumb_word_count"]),
        )
        done += 1
    conn.commit()

    rows = conn.execute(
        """SELECT c.niche_tag, vf.thumb_word_count, vf.thumb_contrast, vf.thumb_saturation, vf.thumb_has_face
           FROM video_features vf JOIN videos v ON v.video_id=vf.video_id
           JOIN channels c ON c.channel_id=v.channel_id
           WHERE vf.thumb_contrast IS NOT NULL"""
    ).fetchall()
    print(f"[thumbs] analyzed {done} thumbnails")
    for tag in sorted({r["niche_tag"] for r in rows}):
        sub = [r for r in rows if r["niche_tag"] == tag]
        import statistics as st
        wc = [r["thumb_word_count"] for r in sub if r["thumb_word_count"] is not None]
        con = [r["thumb_contrast"] for r in sub]
        sat = [r["thumb_saturation"] for r in sub]
        faces = sum(1 for r in sub if r["thumb_has_face"])
        print(f"  {tag}: n={len(sub)} words p50={st.median(wc) if wc else 'n/a'}, "
              f"contrast p50={st.median(con):.0f}, saturation p50={st.median(sat):.0f}, "
              f"face%={100*faces/len(sub):.0f}")


if __name__ == "__main__":
    main()