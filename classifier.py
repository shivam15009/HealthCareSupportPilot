
from pathlib import Path

import joblib


MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "healthcare_classifier.pkl"
)

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"Healthcare classifier model not found: {MODEL_PATH}"
    )

model = joblib.load(MODEL_PATH)
def get_classification_categories():
    """Return the categories supported by the trained model."""
    return sorted(str(category) for category in model.classes_)


def classify_query(query: str):
    """Classify an operational support ticket."""

    if not isinstance(query, str) or not query.strip():
        return {
            "success": False,
            "category": None,
            "confidence": 0.0,
            "message": "A non-empty ticket description is required.",
        }

    if not hasattr(model, "predict_proba"):
        return {
            "success": False,
            "category": None,
            "confidence": 0.0,
            "message": "The loaded model does not support probabilities.",
        }

    try:
        probabilities = model.predict_proba([query.strip()])[0]
        classes = model.classes_

        if len(probabilities) == 0 or len(classes) == 0:
            raise ValueError("The model returned no predictions.")

        best_index = int(probabilities.argmax())

        return {
            "success": True,
            "category": str(classes[best_index]),
            "confidence": round(
                float(probabilities[best_index]) * 100,
                2,
            ),
            "message": "Operational category identified.",
        }

    except Exception:
        return {
            "success": False,
            "category": None,
            "confidence": 0.0,
            "message": "Classification failed.",
        }
