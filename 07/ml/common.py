import os
import sys
import json
import random
from pathlib import Path

# Set seeds for reproducibility
SEED = 42
os.environ["PYTHONHASHSEED"] = str(SEED)
random.seed(SEED)

try:
    import numpy as np
    np.random.seed(SEED)
except ImportError:
    np = None

try:
    import tensorflow as tf
    tf.random.set_seed(SEED)
except Exception:
    tf = None

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None

try:
    from sklearn.metrics import (
        accuracy_score,
        precision_score,
        recall_score,
        f1_score,
        roc_auc_score,
        confusion_matrix
    )
except Exception:
    accuracy_score = None

# Project paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "reports"

MODELS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_SIZE = (224, 224)
BATCH_SIZE = 32
CLASS_NAMES = ["fake", "genuine"]  # fake=0, genuine=1


def build_binary_model(input_shape=(224, 224, 3)):
    """
    Builds MobileNetV2 architecture with data augmentation layers
    active only during training, followed by mobilenet_v2 preprocessing,
    GlobalAveragePooling2D, Dense(128, relu), Dropout(0.3), Dense(1, sigmoid).
    """
    if tf is None:
        raise RuntimeError("TensorFlow is not installed.")

    data_augmentation = tf.keras.Sequential(
        [
            tf.keras.layers.RandomFlip("horizontal_and_vertical"),
            tf.keras.layers.RandomRotation(0.15),
            tf.keras.layers.RandomZoom(0.15),
            tf.keras.layers.RandomBrightness(0.15),
            tf.keras.layers.RandomContrast(0.15),
        ],
        name="train_augmentation"
    )

    inputs = tf.keras.Input(shape=input_shape, name="input_image")
    # Augmentation layers are active ONLY during training (training=True)
    augmented = data_augmentation(inputs)
    preprocessed = tf.keras.applications.mobilenet_v2.preprocess_input(augmented)

    base_model = tf.keras.applications.MobileNetV2(
        input_shape=input_shape,
        include_top=False,
        weights="imagenet"
    )
    base_model.trainable = False

    x = base_model(preprocessed, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D(name="global_avg_pool")(x)
    x = tf.keras.layers.Dense(128, activation="relu", name="dense_128")(x)
    x = tf.keras.layers.Dropout(0.3, name="dropout_03")(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="output_prob")(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs, name="deepguard_binary_classifier")
    return model, base_model


def count_images_in_dir(path: Path) -> int:
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if not path.is_dir():
        return 0
    return sum(1 for p in path.iterdir() if p.suffix.lower() in valid_exts)


def get_split_counts(category_dir: Path):
    counts = {}
    for split in ["train", "val", "test"]:
        split_dir = category_dir / split
        counts[split] = {
            "fake": count_images_in_dir(split_dir / "fake"),
            "genuine": count_images_in_dir(split_dir / "genuine")
        }
    return counts


def load_datasets(category_dir: Path):
    """
    Loads train, val, test datasets using image_dataset_from_directory
    with explicit class_names=["fake", "genuine"].
    """
    if tf is None:
        raise RuntimeError("TensorFlow is not installed.")

    train_dir = category_dir / "train"
    val_dir = category_dir / "val"
    test_dir = category_dir / "test"

    train_ds = tf.keras.utils.image_dataset_from_directory(
        train_dir,
        labels="inferred",
        label_mode="binary",
        class_names=CLASS_NAMES,
        batch_size=BATCH_SIZE,
        image_size=IMAGE_SIZE,
        shuffle=True,
        seed=SEED
    )

    val_ds = tf.keras.utils.image_dataset_from_directory(
        val_dir,
        labels="inferred",
        label_mode="binary",
        class_names=CLASS_NAMES,
        batch_size=BATCH_SIZE,
        image_size=IMAGE_SIZE,
        shuffle=False
    )

    test_ds = tf.keras.utils.image_dataset_from_directory(
        test_dir,
        labels="inferred",
        label_mode="binary",
        class_names=CLASS_NAMES,
        batch_size=BATCH_SIZE,
        image_size=IMAGE_SIZE,
        shuffle=False
    )

    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.prefetch(buffer_size=autotune)
    val_ds = val_ds.prefetch(buffer_size=autotune)
    test_ds = test_ds.prefetch(buffer_size=autotune)

    return train_ds, val_ds, test_ds


def compute_class_weights(train_counts: dict) -> dict:
    """Computes balanced class weights for fake (0) and genuine (1)."""
    n_fake = train_counts.get("fake", 0)
    n_genuine = train_counts.get("genuine", 0)
    total = n_fake + n_genuine
    if n_fake <= 0 or n_genuine <= 0:
        return {0: 1.0, 1: 1.0}

    w0 = total / (2.0 * n_fake)
    w1 = total / (2.0 * n_genuine)
    return {0: float(w0), 1: float(w1)}


def plot_training_curves(history1, history2, output_path: Path, category: str):
    """Plots and saves loss and accuracy curves for Phase 1 and Phase 2."""
    if plt is None:
        return

    loss = history1.history.get("loss", []) + (history2.history.get("loss", []) if history2 else [])
    val_loss = history1.history.get("val_loss", []) + (history2.history.get("val_loss", []) if history2 else [])
    acc = history1.history.get("accuracy", []) + (history2.history.get("accuracy", []) if history2 else [])
    val_acc = history1.history.get("val_accuracy", []) + (history2.history.get("val_accuracy", []) if history2 else [])

    epochs = range(1, len(loss) + 1)
    phase1_len = len(history1.history.get("loss", []))

    plt.figure(figsize=(12, 5))

    # Loss plot
    plt.subplot(1, 2, 1)
    plt.plot(epochs, loss, label="Train Loss", color="#e74c3c")
    plt.plot(epochs, val_loss, label="Val Loss", color="#c0392b", linestyle="--")
    if history2 and phase1_len > 0:
        plt.axvline(x=phase1_len, color="#7f8c8d", linestyle=":", label="Phase 2 Start")
    plt.title(f"{category.capitalize()} - Loss Curve")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.grid(True, alpha=0.3)
    plt.legend()

    # Accuracy plot
    plt.subplot(1, 2, 2)
    plt.plot(epochs, acc, label="Train Accuracy", color="#2ecc71")
    plt.plot(epochs, val_acc, label="Val Accuracy", color="#27ae60", linestyle="--")
    if history2 and phase1_len > 0:
        plt.axvline(x=phase1_len, color="#7f8c8d", linestyle=":", label="Phase 2 Start")
    plt.title(f"{category.capitalize()} - Accuracy Curve")
    plt.xlabel("Epoch")
    plt.ylabel("Accuracy")
    plt.grid(True, alpha=0.3)
    plt.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_confusion_matrix(cm, output_path: Path, category: str):
    """Plots and saves confusion matrix PNG."""
    if plt is None:
        return

    plt.figure(figsize=(6, 5))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title(f"{category.capitalize()} - Confusion Matrix")
    plt.colorbar()
    tick_marks = np.arange(len(CLASS_NAMES))
    plt.xticks(tick_marks, CLASS_NAMES)
    plt.yticks(tick_marks, CLASS_NAMES)

    thresh = cm.max() / 2.0 if cm.max() > 0 else 1.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            val = cm[i, j]
            color = "white" if val > thresh else "black"
            plt.text(j, i, format(val, "d"), horizontalalignment="center", color=color)

    plt.ylabel("True label")
    plt.xlabel("Predicted label")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def evaluate_test_set(model, test_ds, category: str):
    """Evaluates ONLY on the test split, computing all required metrics."""
    y_true = []
    y_prob = []

    for images, labels in test_ds:
        probs = model.predict(images, verbose=0)
        y_true.extend(labels.numpy().flatten())
        y_prob.extend(probs.flatten())

    y_true = np.array(y_true).astype(int)
    y_prob = np.array(y_prob)
    y_pred = (y_prob >= 0.5).astype(int)

    acc = float(accuracy_score(y_true, y_pred)) if accuracy_score else 0.0
    prec_fake = float(precision_score(y_true, y_pred, pos_label=0, zero_division=0)) if accuracy_score else 0.0
    rec_fake = float(recall_score(y_true, y_pred, pos_label=0, zero_division=0)) if accuracy_score else 0.0
    f1_fake = float(f1_score(y_true, y_pred, pos_label=0, zero_division=0)) if accuracy_score else 0.0

    prec_gen = float(precision_score(y_true, y_pred, pos_label=1, zero_division=0)) if accuracy_score else 0.0
    rec_gen = float(recall_score(y_true, y_pred, pos_label=1, zero_division=0)) if accuracy_score else 0.0
    f1_gen = float(f1_score(y_true, y_pred, pos_label=1, zero_division=0)) if accuracy_score else 0.0

    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0)) if accuracy_score else 0.0
    weighted_f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0)) if accuracy_score else 0.0

    try:
        roc_auc = float(roc_auc_score(y_true, y_prob)) if accuracy_score else 0.0
    except Exception:
        roc_auc = 0.0

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1]) if accuracy_score else np.zeros((2, 2), dtype=int)

    metrics = {
        "accuracy": round(acc, 4),
        "roc_auc": round(roc_auc, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "fake": {
            "precision": round(prec_fake, 4),
            "recall": round(rec_fake, 4),
            "f1": round(f1_fake, 4),
            "support": int(np.sum(y_true == 0))
        },
        "genuine": {
            "precision": round(prec_gen, 4),
            "recall": round(rec_gen, 4),
            "f1": round(f1_gen, 4),
            "support": int(np.sum(y_true == 1))
        },
        "test_samples": int(len(y_true)),
        "confusion_matrix": cm.tolist()
    }

    # Save Confusion Matrix PNG
    cm_path = REPORTS_DIR / f"{category}_confusion_matrix.png"
    plot_confusion_matrix(cm, cm_path, category)

    return metrics


def train_category(
    category: str,
    epochs_phase1: int = 15,
    epochs_phase2: int = 15,
    patience: int = 5,
    dataset_sources: str = "custom"
):
    """
    Standard two-phase training pipeline for any of the 4 product categories.
    Phase 1: Frozen MobileNetV2 base, lr=1e-4.
    Phase 2: Unfreeze last 30 layers, lr=1e-5.
    Evaluates on test split and saves artifacts.
    """
    if tf is None:
        raise RuntimeError("TensorFlow is not installed. Please run: pip install -r ml/requirements-train.txt")

    category = category.lower()
    cat_dir = DATA_DIR / category
    if not cat_dir.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {cat_dir}")

    split_counts = get_split_counts(cat_dir)
    print(f"\n==================================================")
    print(f"Starting Training for Category: {category.upper()}")
    print(f"Split counts: {json.dumps(split_counts, indent=2)}")
    print(f"==================================================")

    train_ds, val_ds, test_ds = load_datasets(cat_dir)
    class_weights = compute_class_weights(split_counts["train"])
    print(f"[CLASS WEIGHTS] Computed: {class_weights}")

    # Build model
    model, base_model = build_binary_model(input_shape=(224, 224, 3))

    # Phase 1: Frozen Base
    print("\n--- PHASE 1: Training top layers (base frozen, lr=1e-4) ---")
    base_model.trainable = False
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss="binary_crossentropy",
        metrics=["accuracy"]
    )

    early_stopping_p1 = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=patience,
        restore_best_weights=True,
        verbose=1
    )

    history1 = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs_phase1,
        class_weight=class_weights,
        callbacks=[early_stopping_p1]
    )

    # Phase 2: Fine-Tuning Last 30 Layers
    print("\n--- PHASE 2: Fine-tuning last 30 layers (lr=1e-5) ---")
    base_model.trainable = True
    for layer in base_model.layers[:-30]:
        layer.trainable = False

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
        loss="binary_crossentropy",
        metrics=["accuracy"]
    )

    early_stopping_p2 = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=patience,
        restore_best_weights=True,
        verbose=1
    )

    history2 = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs_phase2,
        class_weight=class_weights,
        callbacks=[early_stopping_p2]
    )

    # Save training curves PNG
    curve_path = REPORTS_DIR / f"{category}_training_curves.png"
    plot_training_curves(history1, history2, curve_path, category)
    print(f"[REPORT] Saved training curve: {curve_path}")

    # Evaluate ONLY on test split
    print("\n--- EVALUATION ON TEST SPLIT ---")
    test_metrics = evaluate_test_set(model, test_ds, category)
    print(f"Test Accuracy: {test_metrics['accuracy'] * 100:.2f}% | ROC-AUC: {test_metrics['roc_auc']:.4f}")
    print(f"Fake F1: {test_metrics['fake']['f1']:.4f} | Genuine F1: {test_metrics['genuine']['f1']:.4f}")

    # Save reports/<category>_report.json
    report_data = {
        "category": category,
        "split_counts": split_counts,
        "class_weights": class_weights,
        "test_metrics": test_metrics,
        "decision_thresholds": {
            "fake_below": 0.35,
            "genuine_above": 0.65
        }
    }
    report_file = REPORTS_DIR / f"{category}_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"[REPORT] Saved metrics report: {report_file}")

    # Save models/<category>.keras and models/<category>_meta.json
    model_file = MODELS_DIR / f"{category}.keras"
    model.save(model_file)
    print(f"[MODEL] Saved model weights: {model_file}")

    meta_data = {
        "category": category,
        "input_size": [224, 224, 3],
        "class_names": CLASS_NAMES,
        "preprocessing": "mobilenet_v2.preprocess_input",
        "tf_version": getattr(tf, "__version__", "unknown"),
        "keras_version": getattr(tf.keras, "__version__", getattr(tf, "__version__", "unknown")),
        "dataset_sources": dataset_sources,
        "split_counts": split_counts,
        "test_metrics": test_metrics,
        "decision_thresholds": {
            "fake_below": 0.35,
            "genuine_above": 0.65
        }
    }
    meta_file = MODELS_DIR / f"{category}_meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=2)
    print(f"[META] Saved metadata: {meta_file}")

    return model, meta_data
