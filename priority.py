
# ==========================================================
# HEALTHCARE SUPPORT PILOT - PRIORITY MANAGEMENT
# ==========================================================

# Default priority for each ticket category
CATEGORY_DEFAULTS = {
    "Patient Registration": "P3",
    "Laboratory": "P2",
    "Pharmacy": "P2",
    "Billing": "P3",
    "Appointment": "P3",
    "Hospital Network": "P1",
    "Staff Authentication": "P2",
    "Equipment": "P2",
}


# Default severity for each ticket category
CATEGORY_SEVERITY = {
    "Patient Registration": "Medium",
    "Laboratory": "High",
    "Pharmacy": "High",
    "Billing": "Medium",
    "Appointment": "Medium",
    "Hospital Network": "Critical",
    "Staff Authentication": "High",
    "Equipment": "High",
}


# Terms indicating a broad hospital incident
ESCALATION_TERMS = [
    "entire hospital",
    "all departments",
    "emergency department",
    "system wide",
    "hospital-wide",
    "multiple departments",
]


# Terms indicating a low-impact issue
LOW_IMPACT_TERMS = [
    "minor",
    "single workstation",
    "one workstation",
    "one printer",
    "single printer",
    "one scanner",
    "single scanner",
    "display issue",
    "slow",
    "configuration",
]


# ==========================================================
# OPERATIONAL SEVERITY
# ==========================================================

def operational_severity(category: str, query: str) -> str:
    """Determine the operational severity of a ticket."""

    text = (query or "").lower()

    # Broad hospital incidents are critical
    if any(term in text for term in ESCALATION_TERMS):
        return "Critical"

    # Low-impact issues receive low severity
    if any(term in text for term in LOW_IMPACT_TERMS):
        return "Low"

    # Otherwise, use the category's default severity
    return CATEGORY_SEVERITY.get(category, "Medium")


# ==========================================================
# OPERATIONAL PRIORITY
# ==========================================================

def operational_priority(category: str, query: str) -> str:
    """Assign a priority level to a ticket."""

    text = (query or "").lower()

    # Broad hospital incidents receive P1
    if any(term in text for term in ESCALATION_TERMS):
        return "P1"

    # Low-impact issues receive P4
    if any(term in text for term in LOW_IMPACT_TERMS):
        return "P4"

    # Otherwise, use the category's default priority
    return CATEGORY_DEFAULTS.get(category, "P3")


# ==========================================================
# HUMAN ESCALATION
# ==========================================================

def should_escalate(query: str, confidence: float) -> bool:
    """Determine whether a ticket needs human review."""

    text = (query or "").lower()

    # Check for broad operational impact
    broad_impact = any(
        term in text
        for term in ESCALATION_TERMS
    )

    # Escalate if classifier confidence is below 70%
    if confidence < 70:
        return True

    # Escalate broad operational incidents
    if broad_impact:
        return True

    # No escalation based on these two checks alone
    return False
