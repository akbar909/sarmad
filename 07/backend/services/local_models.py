import os
import io
import json
from pathlib import Path

# Model cache: str(model_path) -> tf.keras.Model
_MODELS_CACHE = {}
_META_CACHE = {}


def _get_models_dir() -> Path:
    """
    Returns the models directory path.
    Reads env DEEPGUARD_MODELS_DIR; if not set, uses ../ml/models relative to the backend folder.
    """
    env_dir = os.environ.get("DEEPGUARD_MODELS_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    # backend/services/local_models.py -> backend/services -> backend
    backend_dir = Path(__file__).resolve().parent.parent
    return (backend_dir / ".." / "ml" / "models").resolve()


def _load_model(model_path: Path):
    """Loads and caches a Keras model safely using trained weights."""
    path_str = str(model_path)
    if path_str in _MODELS_CACHE:
        return _MODELS_CACHE[path_str]

    os.environ.setdefault("KERAS_BACKEND", "torch")
    import keras

    weights_path = model_path.parent / "model.weights.h5"
    if not weights_path.exists():
        import zipfile
        with zipfile.ZipFile(model_path, "r") as z:
            z.extract("model.weights.h5", model_path.parent)

    inputs = keras.Input(shape=(224, 224, 3), name="input_image")
    base_model = keras.applications.MobileNetV2(
        input_shape=(224, 224, 3), include_top=False, weights=None
    )
    x = base_model(inputs, training=False)
    x = keras.layers.GlobalAveragePooling2D(name="global_avg_pool")(x)
    x = keras.layers.Dense(128, activation="relu", name="dense_128")(x)
    x = keras.layers.Dropout(0.3, name="dropout_03")(x)
    outputs = keras.layers.Dense(1, activation="sigmoid", name="output_prob")(x)
    model = keras.Model(inputs=inputs, outputs=outputs, name="deepguard_binary_classifier")
    model.load_weights(str(weights_path))

    _MODELS_CACHE[path_str] = model
    return model


def _load_meta(meta_path: Path) -> dict:
    """Loads and caches metadata JSON safely."""
    path_str = str(meta_path)
    if path_str in _META_CACHE:
        return _META_CACHE[path_str]

    if meta_path.is_file():
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _META_CACHE[path_str] = data
            return data
    return {}


def predict_local(image_bytes: bytes, category_hint: str | None = None) -> dict | None:
    """
    Performs local inference using the trained footwear model.
    Returns dict or None. NEVER raises an exception under any circumstance.
    """
    try:
        from PIL import Image
        import numpy as np
        os.environ.setdefault("KERAS_BACKEND", "torch")
        import keras
    except Exception as e:
        print(f"[LOCAL MODEL] Dependency import error: {e}")
        return None

    try:
        models_dir = _get_models_dir()
        if not models_dir.is_dir():
            return None

        # Preprocessing: resize to 224x224, convert to RGB,
        # apply mobilenet_v2 preprocessing ((x / 127.5) - 1.0).
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img = img.resize((224, 224))
        img_array = np.array(img, dtype=np.float32)
        batch = np.expand_dims(img_array, axis=0)
        batch = (batch / 127.5) - 1.0

        # ── GATING: decide how to determine the product category ──────────────
        test_only_footwear = os.getenv("DEEPGUARD_LOCAL_TEST_ONLY_FOOTWEAR", "false").lower() in ("true", "1", "yes")

        if test_only_footwear:
            print("[LOCAL] TEST MODE: category gating disabled")
        else:
            cat_classifier_file = models_dir / "category_classifier.keras"

            if cat_classifier_file.is_file():
                # PATH A: Use the trained category classifier
                print("[LOCAL] Gating mode: classifier")

                classifier_model = _load_model(cat_classifier_file)
                meta_classifier = _load_meta(models_dir / "category_classifier_meta.json")
                class_names = meta_classifier.get(
                    "class_names", ["footwear", "electronics", "medicine", "cosmetics"]
                )

                cat_probs = classifier_model.predict(batch, verbose=0)[0]
                max_idx = int(np.argmax(cat_probs))
                max_prob = float(cat_probs[max_idx])

                if max_prob < 0.70:
                    print(f"[LOCAL MODEL] Category confidence too low ({max_prob:.2f} < 0.70) -> fallback to Vision-LLM")
                    return None

                detected_category = (
                    class_names[max_idx].lower() if max_idx < len(class_names) else ""
                )

            else:
                # PATH B: Classifier not available, use category_hint from caller
                print("[LOCAL] Gating mode: hint")

                if not category_hint:
                    print("[LOCAL MODEL] No category_hint provided and classifier absent -> defaulting to footwear model")
                    detected_category = "footwear"
                else:
                    detected_category = category_hint.strip().lower()

            # ── CATEGORY GATE: only answer for "footwear" ─────────────────────────
            # Never let the footwear model judge electronics, medicine, or cosmetics.
            if detected_category != "footwear":
                print(f"[LOCAL MODEL] Category is '{detected_category}' (not Footwear) -> fallback to Vision-LLM")
                return None

        # ── LOAD FOOTWEAR MODEL ────────────────────────────────────────────────
        footwear_model_file = models_dir / "footwear.keras"
        if not footwear_model_file.is_file():
            print("[LOCAL MODEL] footwear.keras not found -> fallback to Vision-LLM")
            return None

        footwear_meta_file = models_dir / "footwear_meta.json"
        cat_meta = _load_meta(footwear_meta_file)

        # Decision thresholds read from meta file, not hardcoded
        thresholds = cat_meta.get("decision_thresholds", {})
        fake_below = float(thresholds.get("fake_below", 0.35))
        genuine_above = float(thresholds.get("genuine_above", 0.65))

        footwear_model = _load_model(footwear_model_file)

        # ── DECISION: p = probability of genuine (class 1) ────────────────────
        prob_arr = footwear_model.predict(batch, verbose=0)
        p = float(prob_arr.flatten()[0])

        if p >= genuine_above:
            result = "Genuine"
            confidence = round(p * 100.0, 2)
        elif p <= fake_below:
            result = "Fake"
            confidence = round((1.0 - p) * 100.0, 2)
        else:
            print(
                f"[LOCAL MODEL] Probability {p:.3f} in uncertain band "
                f"({fake_below} - {genuine_above}) -> fallback to Vision-LLM"
            )
            return None

        # ── EXPLANATION ────────────────────────────────────────────────────────
        explanation = (
            f"Footwear verified by DeepGuard trained model "
            f"(Nike Air Force 1 / Jordan training data) "
            f"with {confidence:.1f}% confidence."
        )

        return {
            "result": result,
            "confidence": confidence,
            "category": "Footwear",
            "explanation": explanation,
            "provider": "local-model"
        }

    except Exception as e:
        print(f"[LOCAL MODEL ERROR] {e}")
        return None
