import sys
from pathlib import Path

# Add current directory to path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from check_dataset import check_dataset

CATEGORY = "footwear"


def main():
    print(f"\n[DeepGuard] Initializing training pipeline for '{CATEGORY}'...")
    passed = check_dataset(CATEGORY)

    if not passed:
        print("\n" + "=" * 70)
        print(f"CANNOT PROCEED WITH TRAINING '{CATEGORY.upper()}'")
        print("Please download and prepare the dataset from Roboflow first using:")
        print(f"  python ml/prepare_data.py roboflow --category footwear --workspace <WORKSPACE> --project <PROJECT> --version <VERSION>")
        print("Remember to set your ROBOFLOW_API_KEY environment variable.")
        print("=" * 70 + "\n")
        sys.exit(0)

    # If dataset check passed, proceed to two-phase training
    from common import train_category
    train_category(CATEGORY, dataset_sources="Roboflow")


if __name__ == "__main__":
    main()
