
from agents.orchestrator import MultiAgentOrchestrator

TEST_CASES = [
    {
        "ticket": (
            "The patient registration portal is not opening on the reception "
            "computers. Staff are unable to create new patient registration records."
        ),
        "category": "Patient Registration",
        "severity": "Medium",
        "priority": "P3",
    },
    {
        "ticket": (
            "The laboratory results system is unavailable and staff cannot "
            "access recently uploaded laboratory reports."
        ),
        "category": "Laboratory",
        "severity": "High",
        "priority": "P2",
    },
    {
        "ticket": (
            "The pharmacy dispensing application is showing an error when "
            "staff try to process prescriptions."
        ),
        "category": "Pharmacy",
        "severity": "High",
        "priority": "P2",
    },
    {
        "ticket": (
            "The hospital billing portal is not loading on the billing "
            "department computers. Staff cannot process billing records."
        ),
        "category": "Billing",
        "severity": "Medium",
        "priority": "P3",
    },
    {
        "ticket": (
            "Staff are unable to access the appointment scheduling system. "
            "New appointments cannot be entered into the system."
        ),
        "category": "Appointment",
        "severity": "Medium",
        "priority": "P3",
    },
    {
        "ticket": (
            "The hospital network is down across multiple departments. "
            "Staff cannot access internal hospital systems."
        ),
        "category": "Hospital Network",
        "severity": "Critical",
        "priority": "P1",
    },
    {
        "ticket": (
            "Staff members are unable to log in to the hospital authentication "
            "system. Login attempts are failing."
        ),
        "category": "Staff Authentication",
        "severity": "High",
        "priority": "P2",
    },
    {
        "ticket": (
            "A printer connected to the laboratory workstation is not printing documents."
        ),
        "category": "Equipment",
        "severity": "Low",
        "priority": "P4",
    },
]


def main():
    orchestrator = MultiAgentOrchestrator()
    category_passes = 0

    print("\\n" + "=" * 65)
    print("HEALTHCARE SUPPORT PILOT - END-TO-END TESTS")
    print("=" * 65)

    for index, case in enumerate(TEST_CASES, start=1):
        print(f"\\nTEST {index}: {case['category']}")
        print("-" * 65)

        try:
            result = orchestrator.run(case["ticket"])
            diagnosis = result.get("diagnosis") or {}

            predicted_category = diagnosis.get("category")
            confidence = diagnosis.get("confidence", 0.0)

            category_ok = predicted_category == case["category"]
            category_passes += int(category_ok)

            print(f"Expected category : {case['category']}")
            print(f"Predicted category: {predicted_category}")
            print(f"Confidence        : {confidence}%")
            print(f"Category test     : {'PASS' if category_ok else 'FAIL'}")

            # Report severity and priority only if the workflow provides them.
            for field, expected in (
                ("severity", case["severity"]),
                ("priority", case["priority"]),
            ):
                actual = result.get(field)
                if actual is None:
                    print(f"{field.capitalize():18}: NOT IMPLEMENTED "
                          f"(expected {expected})")
                else:
                    status = "PASS" if actual == expected else "FAIL"
                    print(f"{field.capitalize():18}: {actual} "
                          f"(expected {expected}) - {status}")

            retrieval = result.get("retrieval") or {}
            evidence = retrieval.get("evidence") or []

            print(f"Retrieved evidence: {len(evidence)} record(s)")
            print(f"Workflow status   : {result.get('status')}")
            print(f"AI resolved       : {result.get('ai_resolved')}")

            if case["category"] == "Hospital Network":
                network_evidence = [
                    item for item in evidence
                    if item.get("category") == "Hospital Network"
                ]
                print(
                    "Network RAG test  : "
                    + ("PASS" if network_evidence else "FAIL")
                )
                print(
                    "Network evidence  : "
                    f"{len(network_evidence)} matching record(s)"
                )

        except Exception as exc:
            print(f"TEST ERROR: {type(exc).__name__}: {exc}")

    print("\\n" + "=" * 65)
    print(f"CATEGORY RESULTS: {category_passes}/{len(TEST_CASES)} correct")
    print("=" * 65)


if __name__ == "__main__":
    main()
