
import pandas as pd
from pathlib import Path

DATA = (
    Path(__file__).resolve().parent
    / "healthcare_support_dataset_1000.csv"
)

df = pd.read_csv(DATA)

for category in [
    "Staff Authentication",
    "Laboratory",
    "Equipment",
    "Hospital Network",
]:
    print(f"\n{'=' * 60}")
    print(f"CATEGORY: {category}")
    print("=" * 60)

    examples = df.loc[
        df["category"] == category,
        "text",
    ].dropna().head(12)

    for index, text in enumerate(examples, start=1):
        print(f"{index}. {text}")