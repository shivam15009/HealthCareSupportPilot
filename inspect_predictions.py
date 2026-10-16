
from classifier import model

tickets = [
    "Hospital staff cannot connect to the internal network.",
    "The pharmacy application is not opening.",
    "A staff member cannot log in to the hospital system.",
    "The printer in the laboratory is offline.",
    "The appointment booking system is unavailable.",
]

for ticket in tickets:
    probabilities = model.predict_proba([ticket])[0]
    classes = model.classes_

    ranked = sorted(
        zip(classes, probabilities),
        key=lambda item: item[1],
        reverse=True,
    )

    print("\n" + "=" * 65)
    print("Ticket:", ticket)
    print("-" * 65)

    for category, probability in ranked[:4]:
        print(f"{category:25s} {probability * 100:6.2f}%")
