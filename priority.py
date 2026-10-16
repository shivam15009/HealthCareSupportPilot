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
    "display-only issue",
    "slow",
    "configuration",
    "maintenance reminder",
    "maintenance status display",
    "administrative inconvenience",
    "administrative tracking",
    "printer is working normally",
    "printing tasks are not affected",
    "no operational impact",
    "no impact to operations",
    "no interruption to operations",
    "no disruption to service",
    "no operational work is disrupted",
    "status display corrected",
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


    # Escalate broad operational incidents.
    if broad_impact:

        return True

    return False