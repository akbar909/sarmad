import os
import sys
import json
from pathlib import Path

# Add ml folder to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import numpy as np
except Exception:
    np = None

try:
    import tensorflow as tf
except Exception:
    tf = None

try:
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
except Exception:
    accuracy_score = None

DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = ["footwear", "medicine", "electronics", "cosmetics"]
CLASS_NAMES = ["fake", "genuine"]
IMAGE_SIZE = (224, 224)
BATCH_SIZE = 32


def evaluate_binary_category(category: str):
    model_file = MODELS_DIR / f"{category}.keras"
    test_dir = DATA_DIR / category / "test"

    if not model_file.is_file():
        return None, "Model file not found"
    if not test_dir.is_dir():
        return None, "Test split folder not found"

    # Count test samples
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    n_fake = sum(1 for p in (test_dir / "fake").iterdir() if p.suffix.lower() in valid_exts) if (test_dir / "fake").is_dir() else 0
    n_gen = sum(1 for p in (test_dir / "genuine").iterdir() if p.suffix.lower() in valid_exts) if (test_dir / "genuine").is_dir() else 0
    total_test = n_fake + n_gen

    if total_test == 0:
        return None, "No test images found"

    if tf is None:
        # Fall back to metadata json if tf not installed in current environment
        meta_file = MODELS_DIR / f"{category}_meta.json"
        if meta_file.is_file():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            tm = meta.get("test_metrics", {})
            return {
                "category": category.capitalize(),
                "accuracy": f"{tm.get('accuracy', 0.0) * 100:.2f}%",
                "precision": f"{tm.get('genuine', {}).get('precision', 0.0):.4f}",
                "recall": f"{tm.get('genuine', {}).get('recall', 0.0):.4f}",
                "f1": f"{tm.get('macro_f1', 0.0):.4f}",
                "test_samples": total_test
            }, "OK (from metadata)"
        return None, "TensorFlow not installed"

    # Load model and run test evaluation
    model = tf.keras.models.load_model(model_file)
    test_ds = tf.keras.utils.image_dataset_from_directory(
        test_dir,
        labels="inferred",
        label_mode="binary",
        class_names=CLASS_NAMES,
        batch_size=BATCH_SIZE,
        image_size=IMAGE_SIZE,
        shuffle=False
    )

    y_true = []
    y_prob = []
    for images, labels in test_ds:
        probs = model.predict(images, verbose=0)
        y_true.extend(labels.numpy().flatten())
        y_prob.extend(probs.flatten())

    y_true = np.array(y_true).astype(int)
    y_prob = np.array(y_prob)
    y_pred = (y_prob >= 0.5).astype(int)

    acc = accuracy_score(y_true, y_pred) if accuracy_score else 0.0
    prec = precision_score(y_true, y_pred, average="macro", zero_division=0) if accuracy_score else 0.0
    rec = recall_score(y_true, y_pred, average="macro", zero_division=0) if accuracy_score else 0.0
    f1 = f1_score(y_true, y_pred, average="macro", zero_division=0) if accuracy_score else 0.0

    return {
        "category": category.capitalize(),
        "accuracy": f"{acc * 100:.2f}%",
        "precision": f"{prec:.4f}",
        "recall": f"{rec:.4f}",
        "f1": f"{f1:.4f}",
        "test_samples": len(y_true)
    }, "OK"


def main():
    print("\n==================================================")
    print("DeepGuard Multi-Category Evaluation Suite")
    print("==================================================")

    results = []
    for cat in CATEGORIES:
        print(f"Evaluating '{cat}'...")
        res, status = evaluate_binary_category(cat)
        if res:
            results.append(res)
            print(f"  -> Success: Acc={res['accuracy']}, F1={res['f1']} ({res['test_samples']} samples)")
        else:
            print(f"  -> Skipped: {status}")

    # Build markdown summary table
    summary_path = REPORTS_DIR / "summary.md"
    md_lines = [
        "# DeepGuard Model Evaluation Summary\n",
        "This evaluation report compiles the held-out test split performance across all trained DeepGuard product categories.\n",
        "| Category | Test Accuracy | Precision | Recall | F1 Score | Test Samples |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |"
    ]

    if results:
        for r in results:
            md_lines.append(
                f"| **{r['category']}** | {r['accuracy']} | {r['precision']} | {r['recall']} | {r['f1']} | {r['test_samples']} |"
            )
    else:
        md_lines.append("| *No models evaluated yet* | - | - | - | - | 0 |")

    md_content = "\n".join(md_lines) + "\n"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n[REPORT GENERATED] Summary report written to: {summary_path}")
    print("\n" + md_content)


if __name__ == "__main__":
    main()
