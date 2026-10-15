import sys
from pathlib import Path

# Add current directory to path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from check_dataset import check_dataset

CATEGORY = "cosmetics"


def main():
    print(f"\n[DeepGuard] Initializing training pipeline for '{CATEGORY}'...")
    passed = check_dataset(CATEGORY)

    if not passed:
        print("\n" + "=" * 70)
        print(f"CANNOT PROCEED WITH TRAINING '{CATEGORY.upper()}'")
        print("This category requires self-collected local data.")
        print("Please organize your images and sources.csv, then run:")
        print("  python ml/prepare_data.py local --category cosmetics --source <FOLDER_WITH_IMAGES>")
        print("\nEnsure <FOLDER_WITH_IMAGES>/sources.csv contains:")
        print("  filename,label,source_group,date")
        print("=" * 70 + "\n")
        sys.exit(0)

    # If dataset check passed, proceed to two-phase training
    from common import train_category
    train_category(CATEGORY, dataset_sources="Local / Curated")


if __name__ == "__main__":
    main()
