from pathlib import Path
import json

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)
from sklearn.pipeline import Pipeline

BASE = Path(__file__).resolve().parents[2]
WORKSPACE = Path(__file__).resolve().parent

ORIGINAL_DATA = BASE / "healthcare_support_dataset_1000.csv"
CANDIDATE_DATA = WORKSPACE / "healthcare_support_dataset_candidate_v2.csv"
EVALUATION_DATA = BASE / "evaluation_100_tickets.csv"

CANDIDATE_MODEL = WORKSPACE / "healthcare_classifier_candidate_fixed.pkl"
RESULTS_CSV = WORKSPACE / "model_comparison_results_fixed.csv"
REPORT_TXT = WORKSPACE / "model_comparison_report_fixed.txt"

def load_dataset(path):
    df = pd.read_csv(path)
    required = {"text", "category"}
    if not required.issubset(df.columns):
        raise ValueError(f"{path} must contain columns {sorted(required)}")

    df = df[["text", "category"]].dropna().copy()
    df["text"] = df["text"].astype(str).str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    df = df[(df["text"] != "") & (df["category"] != "")]

    if df["text"].str.casefold().duplicated().any():
        raise ValueError(f"Duplicate descriptions found in {path}")

    return df

def build_model():
    return Pipeline([
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

def normalize(series):
    return series.astype(str).str.strip().str.casefold()

def main():
    for path in (ORIGINAL_DATA, CANDIDATE_DATA, EVALUATION_DATA):
        if not path.exists():
            raise FileNotFoundError(path)

    original = load_dataset(ORIGINAL_DATA)
    candidate = load_dataset(CANDIDATE_DATA)

    evaluation = pd.read_csv(EVALUATION_DATA)
    required_eval = {"text", "expected_category"}
    if not required_eval.issubset(evaluation.columns):
        raise ValueError(
            f"Evaluation file must contain {sorted(required_eval)}"
        )
    if evaluation[list(required_eval)].isna().any().any():
        raise ValueError("Evaluation text or expected categories are missing")

    evaluation["text"] = evaluation["text"].astype(str).str.strip()
    evaluation["expected_category"] = (
        evaluation["expected_category"].astype(str).str.strip()
    )

    if evaluation["text"].eq("").any():
        raise ValueError("Empty evaluation descriptions found")

    evaluation_texts = set(normalize(evaluation["text"]))
    original_overlap = evaluation_texts.intersection(set(normalize(original["text"])))
    candidate_overlap = evaluation_texts.intersection(set(normalize(candidate["text"])))

    if original_overlap or candidate_overlap:
        raise ValueError(
            "Evaluation descriptions overlap with training data: "
            f"original={len(original_overlap)}, candidate={len(candidate_overlap)}"
        )

    original_labels = set(original["category"])
    candidate_labels = set(candidate["category"])
    expected_labels = set(evaluation["expected_category"])

    if original_labels != candidate_labels:
        raise ValueError("Original and candidate category sets differ")
    if not expected_labels.issubset(original_labels):
        raise ValueError("Evaluation has categories not found in training data")

    models = {
        "original": (build_model(), original),
        "candidate": (build_model(), candidate),
    }

    if CANDIDATE_MODEL.exists() or RESULTS_CSV.exists() or REPORT_TXT.exists():
        raise FileExistsError(
            "A fixed-output file already exists. Rename or review it before running."
        )

    output_rows = [
        {
            "id": row["id"] if "id" in evaluation.columns else i + 1,
            "text": row["text"],
            "expected_category": row["expected_category"],
        }
        for i, (_, row) in enumerate(evaluation.iterrows())
    ]

    report_lines = [
        "HEALTHCARE CLASSIFIER COMPARISON",
        f"Evaluation tickets: {len(evaluation)}",
        f"Original training rows: {len(original)}",
        f"Candidate training rows: {len(candidate)}",
        "",
        "Note: evaluation labels must be independently verified.",
        "This comparison uses the same fixed 100 tickets for both models.",
        "",
    ]

    labels = sorted(original_labels)

    for name, (model, train_df) in models.items():
        model.fit(train_df["text"], train_df["category"])

        predictions = model.predict(evaluation["text"])
        probabilities = model.predict_proba(evaluation["text"])
        confidence = probabilities.max(axis=1) * 100

        accuracy = accuracy_score(
            evaluation["expected_category"], predictions
        )
        report = classification_report(
            evaluation["expected_category"],
            predictions,
            labels=labels,
            zero_division=0,
            output_dict=True,
        )
        matrix = confusion_matrix(
            evaluation["expected_category"],
            predictions,
            labels=labels,
        )

        report_lines.extend([
            "=" * 70,
            name.upper(),
            "=" * 70,
            f"Accuracy: {accuracy:.4f} ({accuracy * 100:.2f}%)",
            f"Mean maximum predicted probability: {confidence.mean():.2f}%",
            f"Median maximum predicted probability: {pd.Series(confidence).median():.2f}%",
            "",
            "Per-category metrics:",
            pd.DataFrame(report).transpose().round(4).to_string(),
            "",
            "Confusion matrix (rows=actual, columns=predicted):",
            f"Category order: {labels}",
            str(matrix),
            "",
        ])

        for i, row in evaluation.iterrows():
            output_rows[i][f"{name}_predicted_category"] = predictions[i]
            output_rows[i][f"{name}_confidence"] = round(float(confidence[i]), 2)
            output_rows[i][f"{name}_correct"] = bool(
                predictions[i] == row["expected_category"]
            )

        if name == "candidate":
            if CANDIDATE_MODEL.exists():
                raise FileExistsError(
                    f"Refusing to overwrite candidate model: {CANDIDATE_MODEL}"
                )
            joblib.dump(model, CANDIDATE_MODEL)


    pd.DataFrame(output_rows).to_csv(RESULTS_CSV, index=False)
    REPORT_TXT.write_text("\n".join(report_lines), encoding="utf-8")

    print("\n".join(report_lines))
    print("\nSaved candidate model:", CANDIDATE_MODEL)
    print("Saved comparison CSV:", RESULTS_CSV)
    print("Saved report:", REPORT_TXT)
    print("\nProduction model and application files were not modified.")

if __name__ == "__main__":
    main()

