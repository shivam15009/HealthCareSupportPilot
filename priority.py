# ==========================================================
# OPERATIONAL SUPPORT SEVERITY AND PRIORITY
# ==========================================================
#
# This module handles only operational/IT support impact.
#
# It does NOT:
# - diagnose diseases
# - predict diseases
# - recommend treatment
# - recommend medication
# - provide medical advice
#
# ==========================================================


CATEGORY_DEFAULTS = {

    "Patient Registration":
        "P3",

    "Laboratory":
        "P2",

    "Pharmacy":
        "P2",

    "Billing":
        "P3",

    "Appointment":
        "P3",

    "Hospital Network":
        "P1",

    "Staff Authentication":
        "P2",

    "Equipment":
        "P2",
}


CATEGORY_SEVERITY = {

    "Patient Registration":
        "Medium",

    "Laboratory":
        "High",

    "Pharmacy":
        "High",

    "Billing":
        "Medium",

    "Appointment":
        "Medium",

    "Hospital Network":
        "Critical",

    "Staff Authentication":
        "High",

    "Equipment":
        "High",
}


ESCALATION_TERMS = [

    "entire hospital",

    "all departments",

    "emergency department",

    "system wide",

    "hospital-wide",

    "multiple departments",
]


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

def operational_severity(
    category: str,
    query: str
):

    text = query.lower()

    # Broad operational impact
    if any(
        term in text
        for term in ESCALATION_TERMS
    ):

        return "Critical"

    # Small operational impact
    if any(
        term in text
        for term in LOW_IMPACT_TERMS
    ):

        return "Low"

    # Category default
    return CATEGORY_SEVERITY.get(
        category,
        "Medium"
    )


# ==========================================================
# OPERATIONAL PRIORITY
# ==========================================================

def operational_priority(
    category: str,
    query: str
):

    text = query.lower()

    # Broad operational impact
    if any(
        term in text
        for term in ESCALATION_TERMS
    ):

        return "P1"

    # Small operational impact
    if any(
        term in text
        for term in LOW_IMPACT_TERMS
    ):

        return "P4"

    return CATEGORY_DEFAULTS.get(
        category,
        "P3"
    )


# ==========================================================
# HUMAN ESCALATION
# ==========================================================

def should_escalate(
    query: str,
    confidence: float
):

    text = query.lower()

    broad_impact = any(
        term in text
        for term in ESCALATION_TERMS
    )

    # Escalate when classifier confidence
    # is below 70%.
    if confidence < 70:

        return True

    # Escalate broad operational incidents.
    if broad_impact:

        return True

    return False