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
    # Explicitly low operational impact
    "no operational impact",
    "no impact to operations",
    "no interruption to operations",
    "no disruption to service",
    "no service interruption",
    "no operational work is disrupted",
    "all core functions remain operational",
    "other functions remain operational",
    "workaround is available",
    "issue is limited to display",
    "issue is limited to appearance",
    "display-only issue",
    "cosmetic issue",
    "minor visual issue",
    "non-critical display issue",

    # Dashboard and user interface
    "dashboard layout issue",
    "dashboard widget order",
    "widgets appear in the wrong order",
    "widget arrangement issue",
    "table column alignment",
    "column alignment issue",
    "incorrect font size",
    "theme preference issue",
    "color scheme preference",
    "layout spacing issue",
    "visual formatting issue",
    "cosmetic formatting issue",
    "interface appearance issue",
    "button alignment issue",
    "non-critical ui issue",

    # Reports and display-only data presentation
    "report formatting issue",
    "report column alignment",
    "report title formatting",
    "report display issue",
    "incorrect date format display",
    "sorting order in report",
    "stale dashboard counter",
    "dashboard count display issue",
    "status display issue",
    "maintenance status display",
    "administrative tracking display",

    # Filters and saved preferences
    "filter does not clear",
    "filter is not clearing",
    "previous filter remains selected",
    "saved display preference",
    "dashboard preference issue",
    "incorrect browser zoom",
    "duplicate browser bookmark",
    "outdated browser bookmark",
    "non-urgent maintenance reminder",
    "maintenance reminder display",

    # Local, non-disruptive peripheral issues
    "one printer with no impact to operations",
    "single printer with no operational impact",
    "one scanner with no impact to operations",
    "single workstation cosmetic issue",
    "single-user display issue",
    "printing tasks are not affected",
    "printer is working normally",
    "no impact to other workstations",

    # Demonstration and test environment
    "demonstration data only",
    "non-clinical demonstration report",
    "test environment display issue",
    "test dashboard layout issue",
    "synthetic test data only",
    "no real patient data is involved",
    "no clinical workflow is affected",
    "no patient care impact",
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