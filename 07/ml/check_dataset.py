import os
import sys
import json
import argparse
import csv
from pathlib import Path
from PIL import Image

try:
    import numpy as np
except ImportError:
    np = None

try:
    import imagehash
except ImportError:
    imagehash = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "reports"

MODELS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MIN_REQUIRED_TRAIN = 100


def get_all_image_paths(category_dir: Path) -> dict:
    """Returns mapping split -> class -> list of Path objects."""
    result = {"train": {"fake": [], "genuine": []},
              "val": {"fake": [], "genuine": []},
              "test": {"fake": [], "genuine": []}}
    if not category_dir.is_dir():
        return result

    for split in ["train", "val", "test"]:
        for cls in ["fake", "genuine"]:
            folder = category_dir / split / cls
            if folder.is_dir():
                for p in folder.iterdir():
                    if p.suffix.lower() in VALID_EXTS and p.is_file():
                        result[split][cls].append(p)
    return result


def inspect_corrupt(file_paths: list, remove_corrupt: bool = False):
    corrupt_files = []
    valid_paths = []
    for p in file_paths:
        try:
            with Image.open(p) as img:
                img.verify()
            with Image.open(p) as img:
                img.load()
            valid_paths.append(p)
        except Exception:
            corrupt_files.append(str(p))
            if remove_corrupt:
                try:
                    p.unlink()
                    print(f"[REMOVED CORRUPT] {p.name}")
                except Exception as e:
                    print(f"[ERROR REMOVING] {p.name}: {e}")
    return valid_paths, corrupt_files


def check_cross_split_duplicates(images_by_split: dict):
    """
    Checks for exact and near duplicates across splits using imagehash (phash <= 4).
    Returns list of leakage records across train-val, train-test, and val-test,
    plus counts per split pair.
    """
    pair_counts = {"train-val": 0, "train-test": 0, "val-test": 0}
    if imagehash is None:
        print("[NOTE] 'imagehash' is not installed; skipping near-duplicate cross-split check.")
        return [], pair_counts

    split_hashes = {"train": [], "val": [], "test": []}
    for split in ["train", "val", "test"]:
        all_paths = images_by_split[split]["fake"] + images_by_split[split]["genuine"]
        for p in all_paths:
            try:
                with Image.open(p) as img:
                    h = imagehash.phash(img)
                    split_hashes[split].append((p, h))
            except Exception:
                continue

    leakage = []

    # 1. train vs val
    for p_tr, h_tr in split_hashes["train"]:
        for p_va, h_va in split_hashes["val"]:
            dist = int(h_tr - h_va)
            if dist <= 4:
                leakage.append({
                    "hash_distance": dist,
                    "file_split_a": "train",
                    "file_path_a": str(p_tr),
                    "file_split_b": "val",
                    "file_path_b": str(p_va)
                })
                pair_counts["train-val"] += 1

    # 2. train vs test
    for p_tr, h_tr in split_hashes["train"]:
        for p_te, h_te in split_hashes["test"]:
            dist = int(h_tr - h_te)
            if dist <= 4:
                leakage.append({
                    "hash_distance": dist,
                    "file_split_a": "train",
                    "file_path_a": str(p_tr),
                    "file_split_b": "test",
                    "file_path_b": str(p_te)
                })
                pair_counts["train-test"] += 1

    # 3. val vs test
    for p_va, h_va in split_hashes["val"]:
        for p_te, h_te in split_hashes["test"]:
            dist = int(h_va - h_te)
            if dist <= 4:
                leakage.append({
                    "hash_distance": dist,
                    "file_split_a": "val",
                    "file_path_a": str(p_va),
                    "file_split_b": "test",
                    "file_path_b": str(p_te)
                })
                pair_counts["val-test"] += 1

    return leakage, pair_counts


def compute_style_metrics(paths: list) -> dict:
    if not paths:
        return {"count": 0, "mean_width": 0, "mean_height": 0, "mean_bytes": 0, "mean_brightness": 0, "jpeg_ratio": 0}

    widths = []
    heights = []
    sizes = []
    brightnesses = []
    jpeg_count = 0

    for p in paths:
        try:
            sz = p.stat().st_size
            sizes.append(sz)
            ext = p.suffix.lower()
            if ext in (".jpg", ".jpeg"):
                jpeg_count += 1

            with Image.open(p) as img:
                w, h = img.size
                widths.append(w)
                heights.append(h)
                gray = img.convert("L")
                if np is not None:
                    b = float(np.mean(np.array(gray)))
                else:
                    pixels = list(gray.getdata())
                    b = sum(pixels) / max(1, len(pixels))
                brightnesses.append(b)
        except Exception:
            continue

    n = max(1, len(widths))
    return {
        "count": len(widths),
        "mean_width": round(sum(widths) / n, 2),
        "mean_height": round(sum(heights) / n, 2),
        "mean_bytes": round(sum(sizes) / n, 2),
        "mean_brightness": round(sum(brightnesses) / n, 2),
        "jpeg_ratio": round(jpeg_count / n, 4)
    }


def check_dataset(category: str, remove_corrupt: bool = False, remove_leaks: bool = False, dedupe_test: bool = False, min_train: int = MIN_REQUIRED_TRAIN) -> bool:
    category = category.lower()
    cat_dir = DATA_DIR / category

    # Graceful check for "no data yet"
    all_images = get_all_image_paths(cat_dir)
    total_found = sum(len(all_images[s][c]) for s in all_images for c in all_images[s])

    if total_found == 0:
        print(f"\n[INFO] No data yet for category '{category}'.")
        print(f"Directory: {cat_dir}")
        print("Please prepare data first using 'python ml/prepare_data.py'.\n")
        return False

    print(f"\n==================================================")
    print(f"Data Quality & Bias Check: {category.upper()}")
    print(f"==================================================")

    # 1. Corrupt image detection
    corrupt_all = []
    for split in ["train", "val", "test"]:
        for cls in ["fake", "genuine"]:
            valid, corrupt = inspect_corrupt(all_images[split][cls], remove_corrupt=remove_corrupt)
            all_images[split][cls] = valid
            corrupt_all.extend(corrupt)

    print(f"[INTEGRITY] Total corrupt images found: {len(corrupt_all)}")

    # 2. Counts check
    counts = {
        s: {c: len(all_images[s][c]) for c in ["fake", "genuine"]}
        for s in ["train", "val", "test"]
    }
    print(f"[COUNTS] Train:   Fake={counts['train']['fake']}, Genuine={counts['train']['genuine']}")
    print(f"[COUNTS] Val:     Fake={counts['val']['fake']}, Genuine={counts['val']['genuine']}")
    print(f"[COUNTS] Test:    Fake={counts['test']['fake']}, Genuine={counts['test']['genuine']}")

    # 3. Near-duplicate / data leakage across splits
    leakage, pair_counts = check_cross_split_duplicates(all_images)

    # Write reports/<category>_leakage.csv
    leakage_csv_path = REPORTS_DIR / f"{category}_leakage.csv"
    with open(leakage_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["hash_distance", "file_split_a", "file_path_a", "file_split_b", "file_path_b"])
        for item in leakage:
            writer.writerow([
                item["hash_distance"],
                item["file_split_a"],
                item["file_path_a"],
                item["file_split_b"],
                item["file_path_b"]
            ])
    print(f"[LEAKAGE REPORT] Written {len(leakage)} leakage pairs to: {leakage_csv_path}")

    # Print per-split-pair counts
    print(f"\n[LEAKAGE BY SPLIT PAIR]")
    print(f"  train-val:  {pair_counts['train-val']}")
    print(f"  train-test: {pair_counts['train-test']}")
    print(f"  val-test:   {pair_counts['val-test']}")
    print(f"  Total:      {len(leakage)}\n")

    # Handle --dedupe-test
    if dedupe_test:
        test_counts_before = {
            "fake": len(all_images["test"]["fake"]),
            "genuine": len(all_images["test"]["genuine"]),
            "total": len(all_images["test"]["fake"]) + len(all_images["test"]["genuine"])
        }
        print("[DEDUPE-TEST] Test class counts BEFORE removal:")
        print(f"  Test: Fake={test_counts_before['fake']}, Genuine={test_counts_before['genuine']} (Total={test_counts_before['total']})")

        # Read reports/<category>_leakage.csv specifically for val-test pairs
        val_test_rows = []
        if leakage_csv_path.is_file():
            with open(leakage_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    s_a = row.get("file_split_a", "")
                    s_b = row.get("file_split_b", "")
                    if (s_a == "val" and s_b == "test") or (s_a == "test" and s_b == "val"):
                        val_test_rows.append(row)
        else:
            for item in leakage:
                s_a = item.get("file_split_a", "")
                s_b = item.get("file_split_b", "")
                if (s_a == "val" and s_b == "test") or (s_a == "test" and s_b == "val"):
                    val_test_rows.append(item)

        test_files_to_remove = set()
        for row in val_test_rows:
            s_a = row.get("file_split_a", "")
            s_b = row.get("file_split_b", "")
            p_a = Path(row.get("file_path_a", ""))
            p_b = Path(row.get("file_path_b", ""))

            # Remove file_path_b (the TEST copy), keep VAL copy untouched
            if s_b == "test":
                test_files_to_remove.add(p_b)
            elif s_a == "test":
                test_files_to_remove.add(p_a)

        removed_test_paths = []
        for p in test_files_to_remove:
            # Safety: strictly remove only from test directory
            if "test" in p.parts and p.is_file():
                try:
                    p.unlink()
                    removed_test_paths.append(str(p))
                except Exception as e:
                    print(f"[ERROR REMOVING TEST DUPE] {p}: {e}")

        # Log every removed file to reports/<category>_removed_test_dupes.txt
        dupes_log_path = REPORTS_DIR / f"{category}_removed_test_dupes.txt"
        with open(dupes_log_path, "w", encoding="utf-8") as f:
            for path_str in sorted(removed_test_paths):
                f.write(path_str + "\n")

        print(f"\n[DEDUPE-TEST] Removed {len(removed_test_paths)} test duplicate files from {category}/test/.")
        print(f"[DEDUPE-TEST] Logged removed files to: {dupes_log_path}")

        # Re-scan paths and print test counts after removal
        all_images = get_all_image_paths(cat_dir)
        counts = {
            s: {c: len(all_images[s][c]) for c in ["fake", "genuine"]}
            for s in ["train", "val", "test"]
        }
        test_counts_after = {
            "fake": counts["test"]["fake"],
            "genuine": counts["test"]["genuine"],
            "total": counts["test"]["fake"] + counts["test"]["genuine"]
        }
        print("[DEDUPE-TEST] Test class counts AFTER removal:")
        print(f"  Test: Fake={test_counts_after['fake']}, Genuine={test_counts_after['genuine']} (Total={test_counts_after['total']})\n")

    # Handle --remove-leaks
    if remove_leaks and leakage:
        print("[COUNTS BEFORE REMOVAL]")
        print(f"  Train: Fake={counts['train']['fake']}, Genuine={counts['train']['genuine']}")
        print(f"  Val:   Fake={counts['val']['fake']}, Genuine={counts['val']['genuine']}")
        print(f"  Test:  Fake={counts['test']['fake']}, Genuine={counts['test']['genuine']}")

        train_files_to_remove = set()
        val_test_warnings = []

        for item in leakage:
            s_a = item["file_split_a"]
            s_b = item["file_split_b"]
            p_a = Path(item["file_path_a"])
            p_b = Path(item["file_path_b"])

            if s_a == "train":
                train_files_to_remove.add(p_a)
            elif s_b == "train":
                train_files_to_remove.add(p_b)
            elif s_a in ("val", "test") and s_b in ("val", "test"):
                val_test_warnings.append((p_a, p_b))

        if val_test_warnings:
            print(f"\n[LEAKAGE WARNING] Found {len(val_test_warnings)} matches between val and test splits:")
            for pa, pb in val_test_warnings[:5]:
                print(f"  - val/test match: {pa.name} <-> {pb.name} (KEPT BOTH - never delete from val or test)")
            if len(val_test_warnings) > 5:
                print(f"  ... and {len(val_test_warnings) - 5} more.")

        removed_paths = []
        for p in train_files_to_remove:
            if p.is_file():
                try:
                    p.unlink()
                    removed_paths.append(str(p))
                except Exception as e:
                    print(f"[ERROR REMOVING] {p}: {e}")

        # Log removed paths to reports/<category>_removed_leaks.txt
        removed_log_path = REPORTS_DIR / f"{category}_removed_leaks.txt"
        with open(removed_log_path, "w", encoding="utf-8") as f:
            for path_str in sorted(removed_paths):
                f.write(path_str + "\n")
        print(f"\n[LEAKAGE CLEANUP] Removed {len(removed_paths)} leaked images from TRAIN split.")
        print(f"[LEAKAGE CLEANUP] Logged removed files to: {removed_log_path}")

        # Re-scan paths and counts after removal
        all_images = get_all_image_paths(cat_dir)
        counts = {
            s: {c: len(all_images[s][c]) for c in ["fake", "genuine"]}
            for s in ["train", "val", "test"]
        }
        print("\n[COUNTS AFTER REMOVAL]")
        print(f"  Train: Fake={counts['train']['fake']}, Genuine={counts['train']['genuine']}")
        print(f"  Val:   Fake={counts['val']['fake']}, Genuine={counts['val']['genuine']}")
        print(f"  Test:  Fake={counts['test']['fake']}, Genuine={counts['test']['genuine']}")

    # Refuse if train < min_train
    if counts["train"]["fake"] < min_train or counts["train"]["genuine"] < min_train:
        reason = (
            f"REFUSED: Category '{category}' training set has insufficient samples.\n"
            f"Requires at least {min_train} images per train class.\n"
            f"Found: train/fake={counts['train']['fake']}, train/genuine={counts['train']['genuine']}.\n"
        )
        print(f"\n[DATASET REFUSAL] {reason}")
        skip_file = MODELS_DIR / f"{category}_SKIPPED.txt"
        with open(skip_file, "w", encoding="utf-8") as f:
            f.write(reason)
        print(f"[STATUS] Written refusal notice to {skip_file}\n")
        return False

    # 4. Style-bias check (genuine vs fake)
    all_genuine = [p for s in ["train", "val", "test"] for p in all_images[s]["genuine"]]
    all_fake = [p for s in ["train", "val", "test"] for p in all_images[s]["fake"]]

    style_gen = compute_style_metrics(all_genuine)
    style_fake = compute_style_metrics(all_fake)

    style_warnings = []
    diff_metrics = {}

    for metric in ["mean_width", "mean_height", "mean_bytes", "mean_brightness", "jpeg_ratio"]:
        vg = style_gen.get(metric, 0)
        vf = style_fake.get(metric, 0)
        max_v = max(abs(vg), abs(vf), 1e-5)
        diff_pct = (abs(vg - vf) / max_v) * 100.0
        diff_metrics[metric] = {
            "genuine": vg,
            "fake": vf,
            "diff_percent": round(diff_pct, 2)
        }
        if diff_pct > 25.0:
            warn = (
                f"Metric '{metric}' differs by {diff_pct:.1f}% between genuine ({vg}) and fake ({vf}). "
                f"Risk: CNN may learn capture source/style instead of counterfeit features!"
            )
            style_warnings.append(warn)
            print(f"[STYLE BIAS WARNING] {warn}")

    if not style_warnings:
        print("[STYLE BIAS CHECK] Passed. Genuine and Fake images have balanced distributions.")

    # 5. Write reports/<category>_data_check.json
    report_data = {
        "category": category,
        "counts": counts,
        "corrupt_images_found": len(corrupt_all),
        "leakage_pairs_found": len(leakage),
        "leakage_by_pair": pair_counts,
        "leakage_details": leakage[:20],
        "style_metrics": diff_metrics,
        "style_warnings": style_warnings,
        "passed": len(style_warnings) == 0 and len(leakage) == 0
    }

    report_path = REPORTS_DIR / f"{category}_data_check.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\n[REPORT] Data check report written to: {report_path}\n")

    return True


def main():
    parser = argparse.ArgumentParser(description="DeepGuard Dataset Quality & Bias Checker")
    parser.add_argument("--category", required=True, help="Product category (footwear, medicine, electronics, cosmetics)")
    parser.add_argument("--remove-corrupt", action="store_true", help="Automatically delete corrupt image files")
    parser.add_argument("--remove-leaks", action="store_true", help="Remove leaked images from TRAIN split only (never delete from val/test)")
    parser.add_argument("--dedupe-test", action="store_true", help="Remove test duplicates from val-test leakage pairs (keeps VAL copy untouched)")
    parser.add_argument("--min-train", type=int, default=MIN_REQUIRED_TRAIN, help="Minimum train images per class required (default 100)")

    args = parser.parse_args()
    check_dataset(
        args.category,
        remove_corrupt=args.remove_corrupt,
        remove_leaks=args.remove_leaks,
        dedupe_test=args.dedupe_test,
        min_train=args.min_train
    )


if __name__ == "__main__":
    main()
