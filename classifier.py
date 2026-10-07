
from pathlib import Path
import joblib

MODEL_PATH = Path(__file__).resolve().parent / "models" / "healthcare_classifier.pkl"
model = joblib.load(MODEL_PATH)

def classify_query(query: str):
    probabilities = model.predict_proba([query])[0]
    classes = model.classes_
    best_index = probabilities.argmax()
    return {
        "category": classes[best_index],
        "confidence": round(float(probabilities[best_index]) * 100, 2)
    }
