
import joblib
import pandas as pd

from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)
from sklearn.calibration import CalibratedClassifierCV

# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent
DATA = BASE / "healthcare_support_dataset_2500.csv"
MODEL_DIR = BASE / "models"
MODEL_PATH = MODEL_DIR / "healthcare_classifier.pkl"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# LOAD AND VALIDATE DATA
# ============================================================

if not DATA.exists():
    raise FileNotFoundError(f"Dataset not found: {DATA}")

df = pd.read_csv(DATA)

required_columns = {"text", "category"}
missing_columns = required_columns - set(df.columns)

if missing_columns:
    raise ValueError(
        f"Dataset is missing columns: {sorted(missing_columns)}"
    )

df = df.dropna(subset=["text", "category"]).copy()

df["text"] = df["text"].astype(str).str.strip()
df["category"] = df["category"].astype(str).str.strip()

df = df[
    (df["text"] != "")
    & (df["category"] != "")
].copy()

if df.empty:
    raise ValueError("No valid training records were found.")

if df["category"].nunique() < 2:
    raise ValueError("At least two categories are required.")

print("=" * 60)
print("DATASET SUMMARY")
print("=" * 60)
print("Total records:", len(df))
print("Unique categories:", df["category"].nunique())
print("\nRecords per category:")
print(df["category"].value_counts().sort_index())

# A stratified split needs at least two records per category.
category_counts = df["category"].value_counts()

if category_counts.min() < 2:
    raise ValueError(
        "Every category needs at least two records for a "
        "stratified train/test split. Add more examples first."
    )

# ============================================================
# TRAIN / TEST SPLIT
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    df["text"],
    df["category"],
    test_size=0.20,
    random_state=42,
    stratify=df["category"],
)

# ============================================================
# BUILD AND TRAIN MODEL
# ============================================================

model = Pipeline([
    (
        "tfidf",
        TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            strip_accents="unicode",
            sublinear_tf=True,
        ),
    ),
    (
        "classifier",
        LogisticRegression(
            max_iter=3000,
            random_state=42,
            class_weight="balanced",
        ),
    ),
])

model.fit(X_train, y_train)

# ============================================================
# EVALUATE HELD-OUT TEST DATA
# ============================================================

predictions = model.predict(X_test)

accuracy = accuracy_score(y_test, predictions)

print("\n" + "=" * 60)
print("HELD-OUT TEST RESULTS")
print("=" * 60)

print(f"Test accuracy: {accuracy:.4f}")

print("\nClassification report:")
print(
    classification_report(
        y_test,
        predictions,
        zero_division=0,
    )
)

labels = sorted(df["category"].unique())

matrix = confusion_matrix(
    y_test,
    predictions,
    labels=labels,
)

print("\nConfusion matrix:")
print("Rows = actual category")
print("Columns = predicted category")
print("Category order:", labels)
print(matrix)

# ============================================================
# TRAIN FINAL MODEL ON ALL LABELED DATA AND SAVE
# ============================================================

# The test metrics above were calculated before this refit.
# Use all available records for the final deployment model.
model.fit(df["text"], df["category"])

joblib.dump(model, MODEL_PATH)

print("\nSaved model:", MODEL_PATH)
print("Final model trained on all records:", len(df))
print("Training complete.")

print("\nSaved model:", MODEL_PATH)
print("Training complete.")

# ============================================================
# TRAIN CALIBRATED MODEL ON ALL LABELED DATA AND SAVE
# ============================================================

calibrated_model = CalibratedClassifierCV(
    estimator=model,
    method="sigmoid",
    cv=5,
)

calibrated_model.fit(df["text"], df["category"])

joblib.dump(calibrated_model, MODEL_PATH)

print("\nSaved calibrated model:", MODEL_PATH)
print("Final model trained using all records:", len(df))
print("Calibration method: sigmoid")
print("Training complete.")