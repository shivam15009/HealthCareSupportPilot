
from agents.diagnosis_agent import DiagnosisAgent

agent = DiagnosisAgent()

tickets = [
    "Hospital staff cannot connect to the internal network.",
    "The pharmacy application is not opening.",
    "A staff member cannot log in to the hospital system.",
    "The printer in the laboratory is offline.",
    "The appointment booking system is unavailable.",
]

for ticket in tickets:
    result = agent.run(ticket)

    print("\nTicket:", ticket)
    print("Success:", result.get("success"))
    print("Category:", result.get("category"))
    print("Confidence:", result.get("confidence"))
    print("Message:", result.get("message"))
