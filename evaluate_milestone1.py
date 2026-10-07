import csv
from collections import Counter
from classifier import classify_query
from priority import operational_priority, should_escalate

DATASET = "evaluation_100_tickets.csv"

rows = []
with open(DATASET, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

correct_category = 0
correct_priority = 0
both_correct = 0
escalated = 0
results = []

for row in rows:
    pred = classify_query(row["text"])
    category = pred["category"]
    confidence = float(pred["confidence"])
    priority = operational_priority(category, row["text"])
    escalate = should_escalate(row["text"], confidence)

    category_ok = category == row["expected_category"]
    priority_ok = priority == row["expected_priority"]
    correct_category += category_ok
    correct_priority += priority_ok
    both_correct += category_ok and priority_ok
    escalated += escalate

    results.append({
        "id": row["id"],
        "text": row["text"],
        "expected_category": row["expected_category"],
        "predicted_category": category,
        "confidence": confidence,
        "expected_priority": row["expected_priority"],
        "predicted_priority": priority,
        "category_correct": category_ok,
        "priority_correct": priority_ok,
        "escalated": escalate,
    })

n = len(rows)
print("=" * 70)
print("HEALTHCARE SUPPORT PILOT - MILESTONE 1 EVALUATION")
print("=" * 70)
print(f"Test tickets: {n}")
print(f"Category accuracy: {correct_category / n * 100:.2f}% ({correct_category}/{n})")
print(f"Priority accuracy: {correct_priority / n * 100:.2f}% ({correct_priority}/{n})")
print(f"Both category + priority correct: {both_correct / n * 100:.2f}% ({both_correct}/{n})")
print(f"Escalation rate: {escalated / n * 100:.2f}% ({escalated}/{n})")
print(f"Average confidence: {sum(r['confidence'] for r in results) / n:.2f}%")
print()

print("CATEGORY RESULTS")
category_counts = Counter(r["expected_category"] for r in results)
for category in sorted(category_counts):
    subset = [r for r in results if r["expected_category"] == category]
    correct = sum(r["category_correct"] for r in subset)
    print(f"{category:22s}: {correct}/{len(subset)} = {correct/len(subset)*100:.2f}%")

print()
print("INCORRECT CLASSIFICATIONS")
errors = [r for r in results if not r["category_correct"]]
if not errors:
    print("None")
else:
    for r in errors:
        print(f"#{r['id']}: expected={r['expected_category']} predicted={r['predicted_category']} confidence={r['confidence']:.2f}%")

print()
print("PRIORITY RESULTS")
priority_counts = Counter(r["expected_priority"] for r in results)
for priority in ["P1", "P2", "P3"]:
    subset = [r for r in results if r["expected_priority"] == priority]
    correct = sum(r["priority_correct"] for r in subset)
    print(f"{priority}: {correct}/{len(subset)} = {correct/len(subset)*100:.2f}%")

print()
print("PRIORITY MISMATCHES")
priority_errors = [r for r in results if not r["priority_correct"]]
if not priority_errors:
    print("None")
else:
    for r in priority_errors:
        print(f"#{r['id']}: expected={r['expected_priority']} predicted={r['predicted_priority']} category={r['predicted_category']}")

with open("evaluation_100_results.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=results[0].keys())
    writer.writeheader()
    writer.writerows(results)

print()
print("Detailed results saved to evaluation_100_results.csv")
