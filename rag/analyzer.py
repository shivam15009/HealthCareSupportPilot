"""
Healthcare Support Pilot
Milestone 2 - Ticket Analyzer

Analyzes healthcare operational support tickets and
assigns an operational support category.

Safety scope:
- Healthcare operational support only
- IT/system/service issues only
- No diagnosis
- No disease prediction
- No treatment recommendations
- No medication recommendations
- No dosage advice
- No personalized medical advice
"""

import re


# ---------------------------------------------------------
# OPERATIONAL SUPPORT CATEGORIES
# ---------------------------------------------------------

CATEGORY_KEYWORDS = {

    "Patient Registration": [
        "registration",
        "register patient",
        "patient registration",
        "registration portal",
        "registration system",
        "admission registration",
        "intake",
        "patient intake",
        "registration error"
    ],

    "Laboratory": [
        "laboratory",
        "lab",
        "lab system",
        "lab portal",
        "lab results",
        "laboratory results",
        "result synchronization",
        "result sync",
        "lab report",
        "lab application"
    ],

    "Pharmacy": [
        "pharmacy",
        "dispensing",
        "dispensing system",
        "pharmacy system",
        "pharmacy application",
        "prescription system",
        "pharmacy portal"
    ],

    "Billing": [
        "billing",
        "billing system",
        "billing portal",
        "invoice",
        "invoice system",
        "insurance portal",
        "insurance",
        "payment system",
        "financial system",
        "billing error"
    ],

    "Appointment": [
        "appointment",
        "appointment system",
        "appointment booking",
        "booking system",
        "schedule appointment",
        "scheduling",
        "appointment portal",
        "reservation system"
    ],

    "Hospital Network": [
        "network",
        "wifi",
        "wi-fi",
        "internet",
        "connectivity",
        "network outage",
        "network connection",
        "server connection",
        "lan",
        "router",
        "switch"
    ],

    "Staff Authentication": [
        "login",
        "log in",
        "sign in",
        "signin",
        "authentication",
        "auth",
        "password",
        "account locked",
        "locked account",
        "staff account",
        "user account",
        "access denied",
        "authentication error"
    ],

    "Equipment": [
        "printer",
        "scanner",
        "workstation",
        "computer",
        "monitor",
        "keyboard",
        "mouse",
        "device",
        "equipment",
        "hardware",
        "barcode scanner",
        "printing",
        "printer error"
    ]
}


# ---------------------------------------------------------
# CATEGORY PRIORITY
# ---------------------------------------------------------

CATEGORY_PRIORITY = {
    "Hospital Network": 1,
    "Staff Authentication": 2,
    "Laboratory": 3,
    "Pharmacy": 4,
    "Equipment": 5,
    "Patient Registration": 6,
    "Billing": 7,
    "Appointment": 8
}


# ---------------------------------------------------------
# TEXT NORMALIZATION
# ---------------------------------------------------------

def normalize_text(text):
    """
    Normalize ticket text before analysis.
    """

    if not text:
        return ""

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9\s-]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ---------------------------------------------------------
# CATEGORY ANALYSIS
# ---------------------------------------------------------

def analyze_ticket(ticket_text):
    """
    Analyze an operational support ticket.

    Returns:

    {
        "category": "...",
        "confidence": 85.0,
        "matched_keywords": [...]
    }
    """

    text = normalize_text(ticket_text)

    if not text:
        return {
            "category": "Unknown",
            "confidence": 0.0,
            "matched_keywords": []
        }

    scores = {}
    matches = {}

    for category, keywords in CATEGORY_KEYWORDS.items():

        score = 0
        matched = []

        for keyword in keywords:

            keyword_normalized = normalize_text(
                keyword
            )

            if not keyword_normalized:
                continue

            # Exact phrase match
            if keyword_normalized in text:
                score += 2
                matched.append(keyword)

        scores[category] = score
        matches[category] = matched

    # -----------------------------------------------------
    # NO MATCH
    # -----------------------------------------------------

    if max(scores.values()) == 0:

        return {
            "category": "Unknown",
            "confidence": 0.0,
            "matched_keywords": []
        }

    # -----------------------------------------------------
    # SORT CATEGORIES
    # -----------------------------------------------------

    ranked = sorted(
        scores.items(),
        key=lambda item: (
            item[1],
            -CATEGORY_PRIORITY.get(
                item[0],
                999
            )
        ),
        reverse=True
    )

    best_category = ranked[0][0]
    best_score = ranked[0][1]

    second_score = (
        ranked[1][1]
        if len(ranked) > 1
        else 0
    )

    # -----------------------------------------------------
    # CONFIDENCE
    # -----------------------------------------------------

    if best_score >= 6:
        confidence = 95.0

    elif best_score >= 4:
        confidence = 90.0

    elif best_score >= 2:
        confidence = 80.0

    else:
        confidence = 65.0

    # Reduce confidence when two categories are very close.
    if (
        second_score > 0
        and best_score == second_score
    ):
        confidence = min(
            confidence,
            60.0
        )

    elif (
        second_score > 0
        and best_score - second_score <= 1
    ):
        confidence = min(
            confidence,
            70.0
        )

    return {
        "category": best_category,
        "confidence": confidence,
        "matched_keywords": matches[best_category]
    }


# ---------------------------------------------------------
# MAIN ANALYZER CLASS
# ---------------------------------------------------------

class TicketAnalyzer:

    def analyze(self, ticket_text):
        """
        Analyze a support ticket.
        """

        return analyze_ticket(ticket_text)


# ---------------------------------------------------------
# CONVENIENCE FUNCTION
# ---------------------------------------------------------

_analyzer = TicketAnalyzer()


def analyze(ticket_text):
    """
    Convenience function for pipeline.py or app.py.

    Example:

        result = analyze(
            "The laboratory system is not syncing results."
        )
    """

    return _analyzer.analyze(ticket_text)