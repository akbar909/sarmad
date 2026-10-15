import os
import sys
import json
import shutil
import random
from pathlib import Path

# Add ml folder to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SEED = 42
random.seed(SEED)
os.environ["PYTHONHASHSEED"] = str(SEED)

try:
    import numpy as np
    np.random.seed(SEED)
except Exception:
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
    from sklearn.metrics import confusion_matrix, classification_report, accuracy_score
except Exception:
    accuracy_score = None

DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "reports"
CATEGORY_DATA_DIR = DATA_DIR / "category"
CATEGORY_EXTRA_DIR = DATA_DIR / "category_extra"

MODELS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = ["footwear", "electronics", "medicine", "cosmetics"]
IMAGE_SIZE = (224, 224)
BATCH_SIZE = 32
VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def assemble_category_dataset():
    """
    Builds data/category/{train,val,test}/{category} by aggregating genuine and fake images
    from each category while strictly preserving their train/val/test splits.
    Also incorporates optional data from data/category_extra/<category>/.
    """
    print("\n[DATA ASSEMBLY] Assembling 4-class category dataset from individual category splits...")
    total_images_assembled = 0

    for split in ["train", "val", "test"]:
        for cat in CATEGORIES:
            target_folder = CATEGORY_DATA_DIR / split / cat
            target_folder.mkdir(parents=True, exist_ok=True)

            # 1. Source from data/<category>/<split>/{genuine,fake}
            cat_split_dir = DATA_DIR / cat / split
            if cat_split_dir.is_dir():
                for subcls in ["fake", "genuine"]:
                    src_sub = cat_split_dir / subcls
                    if src_sub.is_dir():
                        for img_file in src_sub.iterdir():
                            if img_file.suffix.lower() in VALID_EXTS and img_file.is_file():
                                dst_file = target_folder / f"{subcls}_{img_file.name}"
                                if not dst_file.exists():
                                    shutil.copy2(img_file, dst_file)
                                total_images_assembled += 1

            # 2. Source from optional category_extra/<category>
            extra_cat_dir = CATEGORY_EXTRA_DIR / cat
            if extra_cat_dir.is_dir():
                extra_split_dir = extra_cat_dir / split
                if extra_split_dir.is_dir():
                    for img_file in extra_split_dir.iterdir():
                        if img_file.suffix.lower() in VALID_EXTS and img_file.is_file():
                            dst_file = target_folder / f"extra_{img_file.name}"
                            if not dst_file.exists():
                                shutil.copy2(img_file, dst_file)
                            total_images_assembled += 1
                elif split == "train":
                    # If extra images are directly in category_extra/<category>, place in train
                    for img_file in extra_cat_dir.iterdir():
                        if img_file.suffix.lower() in VALID_EXTS and img_file.is_file():
                            dst_file = target_folder / f"extra_{img_file.name}"
                            if not dst_file.exists():
                                shutil.copy2(img_file, dst_file)
                            total_images_assembled += 1

    print(f"[DATA ASSEMBLY] Completed. Total category image instances: {total_images_assembled}")
    return total_images_assembled


def build_multiclass_model(num_classes=4, input_shape=(224, 224, 3)):
    if tf is None:
        raise RuntimeError("TensorFlow is not installed.")

    data_augmentation = tf.keras.Sequential(
        [
            tf.keras.layers.RandomFlip("horizontal"),
            tf.keras.layers.RandomRotation(0.10),
            tf.keras.layers.RandomZoom(0.10),
            tf.keras.layers.RandomBrightness(0.10),
            tf.keras.layers.RandomContrast(0.10),
        ],
        name="category_augmentation"
    )

    inputs = tf.keras.Input(shape=input_shape, name="input_image")
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
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax", name="category_probs")(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs, name="deepguard_category_classifier")
    return model, base_model


def plot_multiclass_confusion_matrix(cm, classes, output_path: Path):
    if plt is None:
        return

    plt.figure(figsize=(7, 6))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("Category Classifier - Confusion Matrix")
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=30)
    plt.yticks(tick_marks, classes)

    thresh = cm.max() / 2.0 if cm.max() > 0 else 1.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            val = cm[i, j]
            color = "white" if val > thresh else "black"
            plt.text(j, i, format(val, "d"), horizontalalignment="center", color=color)

    plt.ylabel("True Category")
    plt.xlabel("Predicted Category")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def train_category_classifier():
    total_images = assemble_category_dataset()
    if total_images == 0:
        print("\n[INFO] No data available to train category classifier.")
        print("Please prepare data for the individual product categories first.")
        print("Optional extra product photos can also be placed in 'ml/data/category_extra/<category>/'.\n")
        sys.exit(0)

    if tf is None:
        print("[ERROR] TensorFlow is not installed. Please run: pip install -r ml/requirements-train.txt")
        sys.exit(1)

    # Check that each category in train has images
    counts = {}
    for cat in CATEGORIES:
        tr_dir = CATEGORY_DATA_DIR / "train" / cat
        cnt = sum(1 for p in tr_dir.iterdir() if p.suffix.lower() in VALID_EXTS) if tr_dir.is_dir() else 0
        counts[cat] = cnt

    print(f"[CATEGORY COUNTS in Train] {counts}")
    if any(cnt < 10 for cnt in counts.values()):
        print("\n[WARNING] Some categories have very few training samples (< 10).")
        print("Please ensure sufficient images are collected across all 4 categories.\n")

    train_ds = tf.keras.utils.image_dataset_from_directory(
        CATEGORY_DATA_DIR / "train",
        labels="inferred",
        label_mode="int",
        class_names=CATEGORIES,
        batch_size=BATCH_SIZE,
        image_size=IMAGE_SIZE,
        shuffle=True,
        seed=SEED
    )

    val_ds = tf.keras.utils.image_dataset_from_directory(
        CATEGORY_DATA_DIR / "val",
        labels="inferred",
        label_mode="int",
        class_names=CATEGORIES,
        batch_size=BATCH_SIZE,
        image_size=IMAGE_SIZE,
        shuffle=False
    )

    test_ds = tf.keras.utils.image_dataset_from_directory(
        CATEGORY_DATA_DIR / "test",
        labels="inferred",
        label_mode="int",
        class_names=CATEGORIES,
        batch_size=BATCH_SIZE,
        image_size=IMAGE_SIZE,
        shuffle=False
    )

    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.prefetch(buffer_size=autotune)
    val_ds = val_ds.prefetch(buffer_size=autotune)
    test_ds = test_ds.prefetch(buffer_size=autotune)

    model, base_model = build_multiclass_model(num_classes=len(CATEGORIES))

    # Phase 1: Train top layers (lr=1e-4)
    print("\n--- PHASE 1: Training top layers (frozen base, lr=1e-4) ---")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )

    early_stopping1 = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=5,
        restore_best_weights=True,
        verbose=1
    )

    model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=15,
        callbacks=[early_stopping1]
    )

    # Phase 2: Fine-tune last 30 layers (lr=1e-5)
    print("\n--- PHASE 2: Fine-tuning last 30 layers (lr=1e-5) ---")
    base_model.trainable = True
    for layer in base_model.layers[:-30]:
        layer.trainable = False

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )

    early_stopping2 = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=5,
        restore_best_weights=True,
        verbose=1
    )

    model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=15,
        callbacks=[early_stopping2]
    )

    # Test Evaluation
    print("\n--- EVALUATION ON TEST SPLIT ---")
    y_true = []
    y_pred = []
    for images, labels in test_ds:
        probs = model.predict(images, verbose=0)
        preds = np.argmax(probs, axis=1)
        y_true.extend(labels.numpy().flatten())
        y_pred.extend(preds.flatten())

    y_true = np.array(y_true).astype(int)
    y_pred = np.array(y_pred).astype(int)

    acc = float(accuracy_score(y_true, y_pred)) if accuracy_score else 0.0
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(CATEGORIES)))) if accuracy_score else np.zeros((4, 4), dtype=int)

    cm_path = REPORTS_DIR / "category_classifier_confusion_matrix.png"
    plot_multiclass_confusion_matrix(cm, CATEGORIES, cm_path)
    print(f"[REPORT] Saved confusion matrix: {cm_path}")

    # Save model and metadata
    model_path = MODELS_DIR / "category_classifier.keras"
    model.save(model_path)
    print(f"[MODEL] Saved category classifier: {model_path}")

    meta = {
        "model_type": "category_classifier",
        "input_size": [224, 224, 3],
        "class_names": CATEGORIES,
        "preprocessing": "mobilenet_v2.preprocess_input",
        "tf_version": getattr(tf, "__version__", "unknown"),
        "test_accuracy": round(acc, 4),
        "test_samples": int(len(y_true)),
        "confusion_matrix": cm.tolist()
    }
    meta_path = MODELS_DIR / "category_classifier_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[META] Saved metadata: {meta_path}\n")


if __name__ == "__main__":
    train_category_classifier()
