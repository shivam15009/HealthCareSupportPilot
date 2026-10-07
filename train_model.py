
import pandas as pd
import joblib
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, classification_report

BASE = Path(__file__).resolve().parent
DATA = BASE / "healthcare_support_dataset.csv"
MODEL_DIR = BASE / "models"
MODEL_DIR.mkdir(exist_ok=True)

df = pd.read_csv(DATA)

X_train, X_test, y_train, y_test = train_test_split(
    df["text"],
    df["category"],
    test_size=0.20,
    random_state=42,
    stratify=df["category"]
)

model = Pipeline([
    ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2))),
    ("classifier", LogisticRegression(max_iter=2000, random_state=42))
])

model.fit(X_train, y_train)
predictions = model.predict(X_test)

accuracy = accuracy_score(y_test, predictions)
print(f"Test accuracy: {accuracy:.4f}")
print(classification_report(y_test, predictions, zero_division=0))

joblib.dump(model, MODEL_DIR / "healthcare_classifier.pkl")
print("Saved:", MODEL_DIR / "healthcare_classifier.pkl")
