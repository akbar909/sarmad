import os
import sys
import csv
import json
import shutil
import random
import argparse
from pathlib import Path
from PIL import Image

SEED = 42
random.seed(SEED)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def map_class_name(raw_name: str, overrides: dict = None) -> str:
    """
    Maps class names:
    - overrides takes precedence
    - containing "counterfeit" or "fake" -> fake
    - containing "authentic", "original", "genuine", "real" -> genuine
    - otherwise -> None (skipped)
    """
    raw_lower = raw_name.strip().lower()

    if overrides and raw_lower in overrides:
        val = overrides[raw_lower].strip().lower()
        if val in ("fake", "genuine"):
            return val
        return None

    if "counterfeit" in raw_lower or "fake" in raw_lower:
        return "fake"
    if any(k in raw_lower for k in ["authentic", "original", "genuine", "real"]):
        return "genuine"

    return None


def print_mapping_table(mapping_stats: dict):
    print("\n" + "=" * 65)
    print(f"{'Original Class Name':<35} | {'Mapped To':<12} | {'Count':<8}")
    print("-" * 65)
    for name, info in sorted(mapping_stats.items()):
        target = info["target"] or "[SKIPPED]"
        count = info["count"]
        print(f"{name:<35} | {target:<12} | {count:<8}")
    print("=" * 65 + "\n")


def prepare_roboflow(args):
    """
    Downloads dataset from Roboflow using ROBOFLOW_API_KEY from environment.
    Supports classification folders and YOLO / COCO object detection cropping.
    Keeps Roboflow train/valid/test splits (valid -> val).
    """
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        print("\n[ERROR] ROBOFLOW_API_KEY environment variable is not set.")
        print("Please set your API key in your terminal before running this script:")
        print("  Windows PowerShell: $env:ROBOFLOW_API_KEY=\"your_key_here\"")
        print("  Windows CMD:        set ROBOFLOW_API_KEY=your_key_here")
        print("  Linux/Mac:          export ROBOFLOW_API_KEY=\"your_key_here\"")
        sys.exit(1)

    try:
        from roboflow import Roboflow
    except ImportError:
        print("\n[ERROR] 'roboflow' package is not installed.")
        print("Please install dependencies: pip install -r ml/requirements-train.txt")
        sys.exit(1)

    category = args.category.lower()
    dest_dir = DATA_DIR / category
    for split in ["train", "val", "test"]:
        (dest_dir / split / "fake").mkdir(parents=True, exist_ok=True)
        (dest_dir / split / "genuine").mkdir(parents=True, exist_ok=True)

    overrides = {}
    if args.map:
        map_path = Path(args.map)
        if map_path.is_file():
            try:
                with open(map_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    overrides = {k.lower(): v.lower() for k, v in data.items()}
                print(f"[MAP] Loaded {len(overrides)} mapping overrides from {map_path}")
            except Exception as e:
                print(f"[MAP WARNING] Could not parse map file: {e}")

    temp_download_dir = BASE_DIR / "temp_downloads" / f"roboflow_{category}"
    temp_download_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[ROBOFLOW] Connecting to workspace='{args.workspace}', project='{args.project}', version={args.version}...")
    # Initialize without printing the key
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(args.workspace).project(args.project)
    version = project.version(int(args.version))

    # Download classification or yolov8 format
    print("[ROBOFLOW] Downloading dataset files...")
    # Attempt classification download first
    try:
        download_res = version.download(model_format="folder", location=str(temp_download_dir))
        download_path = Path(download_res.location)
    except Exception:
        print("[ROBOFLOW] Folder format not available, attempting yolov8 format...")
        download_res = version.download(model_format="yolov8", location=str(temp_download_dir))
        download_path = Path(download_res.location)

    print(f"[ROBOFLOW] Dataset downloaded to: {download_path}")

    mapping_stats = {}

    def record_stat(raw_name, target):
        if raw_name not in mapping_stats:
            mapping_stats[raw_name] = {"target": target, "count": 0}
        mapping_stats[raw_name]["count"] += 1

    # Check structure
    split_map = {"train": "train", "valid": "val", "val": "val", "test": "test"}

    # Detection 1: Check if YOLO structure (images and labels)
    data_yaml = download_path / "data.yaml"
    if data_yaml.is_file():
        print("[ROBOFLOW] Detected YOLO Object Detection format. Cropping annotated boxes...")
        import yaml
        with open(data_yaml, "r", encoding="utf-8") as yf:
            yaml_content = yaml.safe_load(yf)
        names = yaml_content.get("names", [])
        if isinstance(names, dict):
            names = [names[k] for k in sorted(names.keys())]

        for rf_split, target_split in split_map.items():
            img_dir = download_path / rf_split / "images"
            lbl_dir = download_path / rf_split / "labels"
            if not img_dir.is_dir():
                continue

            for img_file in img_dir.iterdir():
                if img_file.suffix.lower() not in VALID_EXTS:
                    continue
                lbl_file = lbl_dir / f"{img_file.stem}.txt"
                if not lbl_file.is_file():
                    continue

                try:
                    with Image.open(img_file) as img:
                        img_w, img_h = img.size
                        with open(lbl_file, "r", encoding="utf-8") as lf:
                            for idx, line in enumerate(lf):
                                parts = line.strip().split()
                                if len(parts) < 5:
                                    continue
                                class_id = int(parts[0])
                                raw_class = names[class_id] if class_id < len(names) else f"class_{class_id}"
                                mapped = map_class_name(raw_class, overrides)
                                record_stat(raw_class, mapped)

                                if not mapped:
                                    continue

                                xc, yc, w, h = map(float, parts[1:5])
                                xmin = max(0, int((xc - w / 2.0) * img_w))
                                ymin = max(0, int((yc - h / 2.0) * img_h))
                                xmax = min(img_w, int((xc + w / 2.0) * img_w))
                                ymax = min(img_h, int((yc + h / 2.0) * img_h))

                                if xmax - xmin < 10 or ymax - ymin < 10:
                                    continue

                                crop = img.crop((xmin, ymin, xmax, ymax))
                                out_name = f"{img_file.stem}_box{idx}.jpg"
                                out_path = dest_dir / target_split / mapped / out_name
                                crop.convert("RGB").save(out_path, "JPEG", quality=95)
                except Exception as e:
                    print(f"[WARN] Error cropping {img_file.name}: {e}")
    else:
        # Classification folder format
        print("[ROBOFLOW] Detected classification folder format...")
        for rf_split, target_split in split_map.items():
            split_folder = download_path / rf_split
            if not split_folder.is_dir():
                continue

            for class_folder in split_folder.iterdir():
                if not class_folder.is_dir():
                    continue
                raw_name = class_folder.name
                mapped = map_class_name(raw_name, overrides)

                for img_file in class_folder.iterdir():
                    if img_file.suffix.lower() not in VALID_EXTS:
                        continue
                    record_stat(raw_name, mapped)
                    if mapped:
                        out_path = dest_dir / target_split / mapped / f"{raw_name}_{img_file.name}"
                        shutil.copy2(img_file, out_path)

    print_mapping_table(mapping_stats)
    print(f"[SUCCESS] Dataset prepared for {category} at: {dest_dir}")


def prepare_local(args):
    """
    Prepares local self-collected images:
    Reads FOLDER/genuine and FOLDER/fake (or as mapped in sources.csv).
    Requires sources.csv (filename,label,source_group,date).
    Splits 70/15/15 stratified BY source_group, ensuring photos of the same item/session/seller
    never end up in different splits.
    """
    category = args.category.lower()
    src_dir = Path(args.source).resolve()
    if not src_dir.is_dir():
        print(f"[ERROR] Source folder does not exist: {src_dir}")
        sys.exit(1)

    csv_file = args.csv if args.csv else (src_dir / "sources.csv")
    csv_path = Path(csv_file).resolve()

    if not csv_path.is_file():
        print("\n[ERROR] sources.csv not found!")
        print(f"Looked for: {csv_path}")
        print("\nRequired CSV format (sources.csv):")
        print("filename,label,source_group,date")
        print("img01.jpg,genuine,seller_A_session1,2026-01-10")
        print("img02.jpg,fake,seller_B_session1,2026-01-11")
        print("\nStratifying by source_group ensures multiple photos from the same seller,")
        print("item, or photo session do not leak across train, val, and test splits.")
        sys.exit(1)

    # Read sources.csv
    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = row.get("filename", "").strip()
            lbl = row.get("label", "").strip().lower()
            grp = row.get("source_group", "").strip()
            dt = row.get("date", "").strip()
            if fn and lbl in ("fake", "genuine") and grp:
                records.append({
                    "filename": fn,
                    "label": lbl,
                    "source_group": grp,
                    "date": dt
                })

    if not records:
        print("[ERROR] No valid rows found in sources.csv with label 'fake' or 'genuine'.")
        sys.exit(1)

    dest_dir = DATA_DIR / category
    for split in ["train", "val", "test"]:
        (dest_dir / split / "fake").mkdir(parents=True, exist_ok=True)
        (dest_dir / split / "genuine").mkdir(parents=True, exist_ok=True)

    print(f"\n[LOCAL] Processing {len(records)} records for category '{category}' from {src_dir}...")

    # Group by label, then stratify by source_group
    for target_label in ["fake", "genuine"]:
        label_records = [r for r in records if r["label"] == target_label]
        groups = list(set(r["source_group"] for r in label_records))
        random.seed(SEED)
        random.shuffle(groups)

        n_groups = len(groups)
        n_train = max(1, int(0.70 * n_groups)) if n_groups >= 3 else n_groups
        n_val = max(1, int(0.15 * n_groups)) if n_groups >= 3 else 0
        n_test = n_groups - n_train - n_val

        if n_groups >= 3 and n_test < 1:
            n_test = 1
            if n_train > 1:
                n_train -= 1

        train_groups = set(groups[:n_train])
        val_groups = set(groups[n_train:n_train + n_val])
        test_groups = set(groups[n_train + n_val:])

        print(f"[{target_label.upper()}] Groups: Total={n_groups} | Train={len(train_groups)}, Val={len(val_groups)}, Test={len(test_groups)}")

        copied_counts = {"train": 0, "val": 0, "test": 0}
        for rec in label_records:
            grp = rec["source_group"]
            if grp in train_groups:
                target_split = "train"
            elif grp in val_groups:
                target_split = "val"
            else:
                target_split = "test"

            # Locate file in source directory or subfolders
            fn = rec["filename"]
            candidates = [
                src_dir / fn,
                src_dir / target_label / fn,
                src_dir / "images" / fn
            ]
            src_file = next((c for c in candidates if c.is_file()), None)
            if not src_file:
                # Search recursively in src_dir
                found = list(src_dir.rglob(fn))
                if found:
                    src_file = found[0]

            if src_file:
                dst_file = dest_dir / target_split / target_label / src_file.name
                shutil.copy2(src_file, dst_file)
                copied_counts[target_split] += 1
            else:
                print(f"[WARN] File not found: {fn}")

        print(f"[{target_label.upper()}] Copied images -> Train: {copied_counts['train']}, Val: {copied_counts['val']}, Test: {copied_counts['test']}")

    print(f"\n[SUCCESS] Local dataset prepared successfully for '{category}' at: {dest_dir}")


def prepare_folder(args):
    """
    Prepares dataset from an existing Roboflow classification folder export.
    Keeps splits: train, valid (-> val), test.
    Maps by keyword (case-insensitive):
      contains 'fake' and NOT 'original' -> fake
      contains 'original' and NOT 'fake' -> genuine
      otherwise -> SKIP with warning
    """
    category = args.category.lower()
    source_dir = Path(args.source).resolve()

    if not source_dir.is_dir():
        print(f"[ERROR] Source folder does not exist: {source_dir}")
        sys.exit(1)

    dest_dir = DATA_DIR / category
    for split in ["train", "val", "test"]:
        (dest_dir / split / "fake").mkdir(parents=True, exist_ok=True)
        (dest_dir / split / "genuine").mkdir(parents=True, exist_ok=True)

    # Note: source Roboflow export has valid, target is val
    split_map = [("train", "train"), ("valid", "val"), ("val", "val"), ("test", "test")]
    seen_target_splits = set()
    table_rows = []
    final_counts = {
        "train": {"fake": 0, "genuine": 0},
        "val": {"fake": 0, "genuine": 0},
        "test": {"fake": 0, "genuine": 0}
    }

    print(f"\n[FOLDER] Processing Roboflow export from: {source_dir}")
    print(f"[FOLDER] Destination: {dest_dir}\n")

    for src_split_name, target_split in split_map:
        if target_split in seen_target_splits and src_split_name == "val":
            # Avoid processing both valid and val if both matched
            continue
        src_split_dir = source_dir / src_split_name
        if not src_split_dir.is_dir():
            continue
        seen_target_splits.add(target_split)

        for class_dir in sorted(src_split_dir.iterdir()):
            if not class_dir.is_dir():
                continue

            folder_name = class_dir.name
            name_lower = folder_name.lower()
            has_fake = "fake" in name_lower
            has_orig = "original" in name_lower

            if has_fake and not has_orig:
                mapped_label = "fake"
            elif has_orig and not has_fake:
                mapped_label = "genuine"
            else:
                mapped_label = None
                print(f"[SKIP WARNING] Ambiguous folder '{folder_name}' in '{src_split_name}' (contains fake={has_fake}, original={has_orig}) -> SKIPPED")

            # Collect matching image files
            images = [p for p in class_dir.iterdir() if p.suffix.lower() in VALID_EXTS and p.is_file()]
            img_count = len(images)

            table_rows.append({
                "split": src_split_name,
                "folder": folder_name,
                "mapped": mapped_label if mapped_label else "[SKIPPED]",
                "count": img_count
            })

            if mapped_label:
                out_dir = dest_dir / target_split / mapped_label
                for img_p in images:
                    dst_file = out_dir / f"{folder_name}_{img_p.name}"
                    shutil.copy2(img_p, dst_file)
                final_counts[target_split][mapped_label] += img_count

    # Print Table: split | source folder | mapped label | image count
    print("\n" + "=" * 80)
    print(f"{'Split':<10} | {'Source Folder':<40} | {'Mapped Label':<14} | {'Image Count':<10}")
    print("-" * 80)
    for row in table_rows:
        print(f"{row['split']:<10} | {row['folder']:<40} | {row['mapped']:<14} | {row['count']:<10}")
    print("=" * 80 + "\n")

    # Final counts per split and class
    print("Final Processed Counts:")
    total_fake = 0
    total_genuine = 0
    for s in ["train", "val", "test"]:
        f_cnt = final_counts[s]["fake"]
        g_cnt = final_counts[s]["genuine"]
        total_fake += f_cnt
        total_genuine += g_cnt
        print(f"  {s:<5} -> Fake: {f_cnt:<6} | Genuine: {g_cnt:<6}")

    print(f"\nTotal Copied -> Fake: {total_fake} | Genuine: {total_genuine}")

    if total_fake == 0 or total_genuine == 0:
        missing = "fake" if total_fake == 0 else "genuine"
        if total_fake == 0 and total_genuine == 0:
            missing = "fake and genuine"
        print(f"\n[ERROR] Zero {missing} images were copied! Dataset preparation cannot proceed.")
        sys.exit(1)

    print(f"\n[SUCCESS] Dataset prepared successfully for '{category}' at: {dest_dir}\n")


def main():
    parser = argparse.ArgumentParser(description="DeepGuard Data Preparation Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Roboflow subcommand
    rf_parser = subparsers.add_parser("roboflow", help="Download and prepare dataset from Roboflow")
    rf_parser.add_argument("--category", required=True, choices=["footwear", "medicine", "electronics", "cosmetics"])
    rf_parser.add_argument("--workspace", required=True, help="Roboflow workspace name")
    rf_parser.add_argument("--project", required=True, help="Roboflow project name")
    rf_parser.add_argument("--version", required=True, help="Roboflow project version number")
    rf_parser.add_argument("--map", default=None, help="Optional JSON file with class name overrides")

    # Local subcommand
    local_parser = subparsers.add_parser("local", help="Prepare self-collected local dataset with source_group stratification")
    local_parser.add_argument("--category", required=True, choices=["footwear", "medicine", "electronics", "cosmetics"])
    local_parser.add_argument("--source", required=True, help="Path to source folder containing images")
    local_parser.add_argument("--csv", default=None, help="Optional custom path to sources.csv")

    # Folder subcommand
    folder_parser = subparsers.add_parser("folder", help="Prepare dataset from an existing Roboflow classification folder export")
    folder_parser.add_argument("--category", required=True, choices=["footwear", "medicine", "electronics", "cosmetics"])
    folder_parser.add_argument("--source", required=True, help="Path to Roboflow folder export containing train/valid/test")

    args = parser.parse_args()

    if args.command == "roboflow":
        prepare_roboflow(args)
    elif args.command == "local":
        prepare_local(args)
    elif args.command == "folder":
        prepare_folder(args)


if __name__ == "__main__":
    main()
