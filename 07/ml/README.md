# DeepGuard Machine Learning Pipeline

A modular, reproducible machine learning training and evaluation pipeline for **DeepGuard** product authentication.

Supports 4 core product categories:
- **Footwear**
- **Medicine**
- **Electronics**
- **Cosmetics**

Plus a unified 4-class **Category Classifier**.

---

## 1. Directory Structure

```text
ml/
├── data/
│   ├── footwear/         # {train, val, test}/{fake, genuine}/
│   ├── medicine/         # {train, val, test}/{fake, genuine}/
│   ├── electronics/      # {train, val, test}/{fake, genuine}/
│   ├── cosmetics/        # {train, val, test}/{fake, genuine}/
│   ├── category/         # Auto-assembled 4-class dataset
│   └── category_extra/   # Optional additional category images
├── models/               # Saved .keras models and metadata JSONs
├── reports/              # Performance reports, confusion matrices, and plots
├── common.py             # Shared MobileNetV2 architecture and training loops
├── prepare_data.py       # Roboflow and local data preparation pipelines
├── check_dataset.py      # Quality gate, leakage detector, and style bias checks
├── train_footwear.py     # Footwear training script
├── train_medicine.py     # Medicine training script
├── train_electronics.py  # Electronics training script
├── train_cosmetics.py    # Cosmetics training script
├── train_category_classifier.py # 4-class softmax classifier
├── evaluate.py           # Evaluation runner generating reports/summary.md
├── requirements-train.txt# Training environment dependencies
└── README.md
```

---

## 2. Environment Setup

To keep the production FastAPI backend lightweight, training dependencies are isolated in `ml/requirements-train.txt`:

```bash
pip install -r ml/requirements-train.txt
```

---

## 3. Data Preparation

### A. Roboflow Datasets (`footwear`, `medicine`)
Set your `ROBOFLOW_API_KEY` in your environment (never hardcoded):

**Windows PowerShell:**
```powershell
$env:ROBOFLOW_API_KEY="your_api_key_here"
```

**Windows Command Prompt:**
```cmd
set ROBOFLOW_API_KEY=your_api_key_here
```

**Run preparation:**
```bash
python ml/prepare_data.py roboflow --category footwear --workspace <WORKSPACE> --project <PROJECT> --version <VERSION>
python ml/prepare_data.py roboflow --category medicine --workspace <WORKSPACE> --project <PROJECT> --version <VERSION>
```
*Note:* If the dataset is an object detection dataset (YOLO format), annotated bounding boxes are automatically cropped into individual class instances. Original splits (`train`, `valid` -> `val`, `test`) are preserved to prevent data leakage.

### B. Local Self-Collected Datasets (`electronics`, `cosmetics`)
For custom images, place them in a folder with a `sources.csv` file:

```csv
filename,label,source_group,date
phone_front.jpg,genuine,seller_apple_official,2026-01-15
phone_back.jpg,genuine,seller_apple_official,2026-01-15
fake_charger.jpg,fake,street_vendor_market_01,2026-01-20
```

**Run preparation:**
```bash
python ml/prepare_data.py local --category electronics --source path/to/images_folder
python ml/prepare_data.py local --category cosmetics --source path/to/images_folder
```
*Note:* The pipeline stratifies by `source_group` (70% train / 15% val / 15% test) so photos of the same item, seller, or photography session never cross splits.

---

## 4. Dataset Integrity & Style-Bias Audit

Run the automated data checker before every training run:

```bash
python ml/check_dataset.py --category footwear
python ml/check_dataset.py --category medicine
python ml/check_dataset.py --category electronics
python ml/check_dataset.py --category cosmetics
```

### What this checks:
1. **Minimum Samples:** Refuses to train if any train class has fewer than 100 images (writes `models/<category>_SKIPPED.txt`).
2. **Image Integrity:** Identifies corrupt files; use `--remove-corrupt` to delete them.
3. **Cross-Split Leakage:** Uses perceptual hashing (`imagehash.phash`, hamming distance $\le 4$) to verify images from validation/test sets do not duplicate training images.
4. **Style-Bias Audit:** Compares genuine vs fake for mean dimensions, file size, brightness, and JPEG/PNG format ratio. Warns if any metric differs by $> 25\%$.
5. **JSON Report:** Saves findings to `reports/<category>_data_check.json`.

---

## 5. Model Training

Each binary category classifier uses a two-phase transfer learning workflow on **MobileNetV2**:
- **Phase 1:** Frozen ImageNet base, learning rate $1\times 10^{-4}$.
- **Phase 2:** Unfreeze top 30 layers, learning rate $1\times 10^{-5}$.
- Balanced class weights computed automatically.
- Early stopping on validation loss with `restore_best_weights=True`.

Run individual category training:
```bash
python ml/train_footwear.py
python ml/train_medicine.py
python ml/train_electronics.py
python ml/train_cosmetics.py
```

Train the 4-class Category Classifier:
```bash
python ml/train_category_classifier.py
```

---

## 6. Evaluation & FYP Summary Report

Evaluate all trained models on held-out test splits:
```bash
python ml/evaluate.py
```
This generates `reports/summary.md` with a clean markdown table of test accuracy, precision, recall, and F1 scores ready to include in your FYP documentation.

---

## 7. Backend Integration

The backend safely integrates trained models via `backend/services/local_models.py` without requiring extra server dependencies.

To enable local model inference in the backend API:
```bash
# In your terminal or deployment environment:
set USE_LOCAL_MODELS=true
```

Inference workflow:
1. **Category Prediction:** `category_classifier.keras` classifies the product category. If confidence $< 70\%$, falls through to Vision-LLM.
2. **Authentication:** The category model (`<category>.keras`) predicts genuine probability $p$.
   - $p \ge 0.65 \implies$ **Genuine**
   - $p \le 0.35 \implies$ **Fake**
   - $0.35 < p < 0.65 \implies$ Uncertain band; falls through to Vision-LLM.
