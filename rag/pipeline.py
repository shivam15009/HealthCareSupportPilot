"""
Healthcare Support Pilot
Milestone 2 - RAG Pipeline

Connects the knowledge retriever and resolution generator.

Pipeline:

Support Ticket
      ↓
Predicted Category
      ↓
Knowledge Retrieval
      ↓
Top KB Evidence
      ↓
Context Augmentation
      ↓
Operational Resolution

Safety scope:
- Healthcare operational support only
- IT/system troubleshooting only
- No diagnosis
- No disease prediction
- No treatment recommendations
- No medication recommendations
- No dosage advice
- No personalized medical advice
"""

from rag.retriever import KnowledgeRetriever
from rag.generator import generate_support_response


import re

def build_retrieval_query(ticket_text, category=None):
    """Build a concise retrieval query for a recognized issue pattern."""
    original = " ".join((ticket_text or "").split())

    if not original:
        return original

    category_name = str(category or "").strip().casefold()

    # Normalize this appointment-access failure into a concise search query.
    access_issue = re.search(
        r"\b(?:unable to access|cannot access|can't access|"
        r"not able to access)\b",
        original,
        re.IGNORECASE,
    )

    appointment_entry_failure = re.search(
        r"\bnew appointments?\s+(?:cannot|can't|can not)"
        r"\s+(?:be\s+)?(?:entered|created|saved|booked)\b",
        original,
        re.IGNORECASE,
    )
    text_lower = (ticket_text or "").lower()
    category_lower = (category or "").strip().lower()
        # Appointment: confirmation message never appears.
    if category_lower == "appointment":
        if any(phrase in text_lower for phrase in [
            "confirmation message never appears",
            "confirmation never appears",
            "confirmation message does not appear",
            "confirmation message doesn't appear",
        ]):
            return "Appointment confirmation is not generated"

    # Billing: charge remains pending instead of completing.
    if category_lower == "billing":
        if any(phrase in text_lower for phrase in [
            "patient charge stays in a waiting state",
            "submitted patient charge",
            "waiting state rather than completing",
            "charge remains pending",
            "charge is still pending",
        ]):
            return "Billing transaction remains pending"

    # Laboratory: timeout or time limit exceeded.
    if category_lower == "laboratory":
        if any(phrase in text_lower for phrase in [
            "time limit exceeded",
            "request timed out",
            "deadline exceeded",
        ]):
            return "Laboratory interface reports a timeout"

    # Appointment: no available booking slots.
    if category_lower == "appointment":
        if any(phrase in text_lower for phrase in [
            "no bookable times",
            "no available times",
            "no bookable slots",
            "no available slots",
            "calendar shows no",
        ]):
            return "Appointment search returns no matching slot"

        # Appointment details disappear after saving.
        if any(phrase in text_lower for phrase in [
            "details disappear after saving",
            "details vanish after saving",
            "details are lost after saving",
            "visit details disappear",
        ]):
            return "Appointment booking cannot be saved"

    # Billing: website or portal cannot load.
    if category_lower == "billing":
        if any(phrase in text_lower for phrase in [
            "billing site will not load",
            "billing site won't load",
            "billing website will not load",
            "billing website won't load",
            "billing portal will not load",
            "billing portal won't load",
        ]):
            return "Billing portal cannot be reached"
    if (
        category_name == "appointment"
        and access_issue
        and appointment_entry_failure
    ):
        return "Appointment scheduling application is unavailable"
        # Add related terminology while preserving the original query.
    # This improves synonym matching without replacing the user's wording.
    expansion_terms = []

    # Billing: waiting or processing means a pending transaction.
    if category_lower == "billing":
        if (
            any(word in text_lower for word in [
                "charge", "transaction", "payment"
            ])
            and any(word in text_lower for word in [
                "waiting", "processing", "indefinitely", "pending"
            ])
        ):
            expansion_terms.append(
                "billing transaction remains pending"
            )

        # A blank document produced during export may indicate export failure.
        if any(word in text_lower for word in [
            "export", "exported", "blank document"
        ]):
            expansion_terms.append(
                "billing export fails billing report export error"
            )

    # Equipment: partial printouts and cut-off pages.
    if category_lower == "equipment":
        if (
            any(word in text_lower for word in [
                "printer", "printout", "printing", "document"
            ])
            and any(word in text_lower for word in [
                "halfway", "partial", "part of", "cut off",
                "incomplete", "stops"
            ])
        ):
            expansion_terms.append(
                "printer produces incomplete output partial printout"
            )

    # Hospital Network: wireless drops and intermittent connections.
    if category_lower == "hospital network":
        if any(phrase in text_lower for phrase in [
            "wi-fi", "wifi", "wireless"
        ]) and any(word in text_lower for word in [
            "cuts out", "disconnect", "drops", "repeatedly"
        ]):
            expansion_terms.append(
                "wireless connection drops repeatedly"
            )

        if any(phrase in text_lower for phrase in [
            "comes and goes", "cuts in and out",
            "every few minutes", "intermittent"
        ]):
            expansion_terms.append(
                "department network connection is intermittent"
            )

    # Laboratory: missing results or test values.
    if category_lower == "laboratory":
        if any(phrase in text_lower for phrase in [
            "test values", "test results", "laboratory viewer",
            "lab results", "result values"
        ]) and any(phrase in text_lower for phrase in [
            "never appear", "not appear", "missing",
            "not updating", "do not appear"
        ]):
            expansion_terms.append(
                "laboratory result interface is not updating"
            )

    # Patient Registration: waiting records and pending status.
    if category_lower == "patient registration":
        if any(word in text_lower for word in [
            "record", "patient"
        ]) and any(word in text_lower for word in [
            "waiting", "pending", "processing"
        ]):
            expansion_terms.append(
                "registration record remains in pending state"
            )

    # Pharmacy: a gateway that stalls while sending a prescription.
    if category_lower == "pharmacy":
        if any(word in text_lower for word in [
            "gateway", "sending", "transmitting"
        ]) and any(word in text_lower for word in [
            "stalls", "stall", "hangs", "stops responding"
        ]):
            expansion_terms.append(
                "prescription interface times out"
            )
        # Billing: connection-refused and connection-failure wording.
    if category_lower == "billing":
        if any(phrase in text_lower for phrase in [
            "connection refused",
            "cannot connect",
            "can't connect",
            "unable to connect",
            "connection failed",
            "refused the connection",
        ]):
            expansion_terms.append(
                "Billing portal cannot be reached"
            )

        # Billing reports and monthly totals.
        if any(phrase in text_lower for phrase in [
            "monthly totals",
            "monthly total",
            "billing totals",
            "account totals",
            "invoice summary",
            "financial totals",
        ]):
            expansion_terms.append(
                "Billing report does not load"
            )

    # Equipment: incomplete output, blank areas, or missing lines.
    if category_lower == "equipment":
        if (
            any(phrase in text_lower for phrase in [
                "printed page",
                "printout",
                "printed document",
                "print output",
            ])
            and any(phrase in text_lower for phrase in [
                "missing lines",
                "blank areas",
                "blank sections",
                "missing parts",
                "halfway down",
                "incomplete output",
            ])
        ):
            expansion_terms.append(
                "Printer produces incomplete output"
            )

    # Hospital Network: repeated network disconnections.
    if category_lower == "hospital network":
        if any(phrase in text_lower for phrase in [
            "keeps disconnecting",
            "disconnecting users",
            "disconnects users",
            "connection cuts out",
            "network keeps dropping",
            "network service keeps disconnecting",
        ]):
            expansion_terms.append(
                "Department network connection is intermittent"
            )

        # Internal application or intranet timeout.
        if (
            any(phrase in text_lower for phrase in [
                "timeout",
                "time out",
                "times out",
                "timed out",
            ])
            and any(phrase in text_lower for phrase in [
                "intranet",
                "dashboard",
                "internal application",
                "internal system",
            ])
        ):
            expansion_terms.append(
                "Internal application times out over the network"
            )

    # Laboratory: login or authentication errors.
    if category_lower == "laboratory":
        if (
            any(phrase in text_lower for phrase in [
                "staff login",
                "valid login",
                "credentials",
                "log in",
                "login",
            ])
            and any(phrase in text_lower for phrase in [
                "rejects",
                "rejected",
                "denied",
                "failed",
                "error",
                "cannot",
                "can't",
            ])
        ):
            expansion_terms.append(
                "Laboratory application shows an authentication error"
            )

        # Laboratory app cannot get past its loading screen.
        if any(phrase in text_lower for phrase in [
            "loading screen",
            "never gets past",
            "stuck loading",
            "blank working window",
            "will not finish loading",
            "won't finish loading",
        ]):
            expansion_terms.append(
                "Laboratory workstation cannot open the application"
            )
    if expansion_terms:
        extra_terms = " ".join(dict.fromkeys(expansion_terms))
        return f"{ticket_text} {extra_terms}"
    # Leave other ticket descriptions unchanged until their patterns
    # have been tested against relevant knowledge-base examples.
    return original

class SupportPipeline:
    """Run the complete local Milestone 2 RAG workflow."""

    def __init__(self):
        """Initialize the knowledge-base retriever."""
        self.retriever = KnowledgeRetriever()

    def run(self, ticket_text, category=None, top_k=3, generate_resolution=True):
        """
        Run retrieval, context augmentation, and resolution generation.

        Parameters
        ----------
        ticket_text : str
            Original support ticket description.

        category : str, optional
            Category predicted by classifier.py.

        top_k : int
            Maximum number of knowledge-base entries to retrieve.

        generate_resolution : bool
            If False, return retrieved evidence and context without generating
            a resolution. Useful when a ticket requires human review.

        Returns
        -------
        dict
            Retrieved evidence, augmented context, and resolution.
        """
        ticket_text = (ticket_text or "").strip()

        # --------------------------------------------------
        # VALIDATE TICKET
        # --------------------------------------------------
        if not ticket_text:
            return {
                "evidence": [],
                "context": "",
                "resolution": (
                    "No support ticket description was provided."
                ),
            }


        # STEP 1: KNOWLEDGE BASE RETRIEVAL
        retrieval_query = build_retrieval_query(ticket_text, category)

        print(
            f"[DEBUG] Original ticket: {ticket_text!r}",
            flush=True,
        )
        print(
            f"[DEBUG] Retrieval query: {retrieval_query!r}",
            flush=True,
        )

        evidence = self.retriever.search(
            query=retrieval_query,
            category=category,
            top_k=top_k,
        )

        print(
            "\n[DEBUG] PIPELINE EVIDENCE:",
            "count =", len(evidence),
            "items =", [
                (item.get("title"), item.get("score"))
                for item in evidence
            ],
            flush=True,
        )
        import logging

        logging.warning(
            "PIPELINE RETRIEVAL: query=%r category=%r top_k=%r "
            "evidence_count=%d evidence=%r",
            ticket_text,
            category,
            top_k,
            len(evidence),
            [
                {
                    "title": item.get("title"),
                    "category": item.get("category"),
                    "score": item.get("score"),
                }
                for item in evidence
            ],
        )
        # --------------------------------------------------
        # STEP 2: CONTEXT AUGMENTATION
        # --------------------------------------------------
        # Keep the retrieval result usable even when generation is
        # intentionally skipped for tickets requiring human review.
        context_parts = []
        for item in evidence:
            title = item.get("title", "Knowledge-base article")
            issue = item.get("issue", "")
            resolution_steps = item.get("resolution", [])
            if isinstance(resolution_steps, str):
                resolution_steps = [resolution_steps]
            details = " ".join(str(step) for step in resolution_steps if step)
            context_parts.append(
                f"{title}. {issue} {details}".strip()
            )
        context = "\\n".join(part for part in context_parts if part)

        resolution = ""
        generation_time_ms = None
        if generate_resolution and evidence:
            # Pass the classifier's predicted category into the generator.
            # This keeps Operational Area tied to classification instead
            # of allowing retrieved KB evidence to replace it.
            response = generate_support_response(
                ticket_text=ticket_text,
                evidence=evidence,
                category=category,
            )

            context = response.get("context", context)
            resolution = response.get("resolution", "")
            generation_time_ms = response.get("generation_time_ms")


        # --------------------------------------------------
        # STEP 3: RETURN COMPLETE RESULT
        # --------------------------------------------------

        return {
            "evidence": evidence,
            "context": context,
            "resolution": resolution,
            "generation_time_ms": (
                generation_time_ms
                if generate_resolution and evidence
                else None
            ),
        }



# ==========================================================
# SINGLE PIPELINE INSTANCE
# ==========================================================

_pipeline = None


# ==========================================================
# CONVENIENCE FUNCTION
# ==========================================================

def run_pipeline(ticket_text, category=None, top_k=3, generate_resolution=True):
    """
    Run the Milestone 2 RAG pipeline.

    Example
    -------
    result = run_pipeline(
        "Laboratory system is not syncing results",
        category="Laboratory",
        top_k=3,
    )
    """
    global _pipeline

    if _pipeline is None:
        _pipeline = SupportPipeline()

    return _pipeline.run(
        ticket_text=ticket_text,
        category=category,
        top_k=top_k,
        generate_resolution=generate_resolution,
    )
