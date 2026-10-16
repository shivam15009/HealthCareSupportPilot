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
from rag.generator import (
    MIN_RELEVANCE,
    build_context,
    extract_steps,
    generate_support_response,
)


class SupportPipeline:
    """Run the complete local Milestone 2 RAG workflow."""

    def __init__(self):
        """Initialize the knowledge-base retriever."""
        self.retriever = KnowledgeRetriever()

    def run(
        self,
        ticket_text,
        category=None,
        top_k=3,
        generate_resolution=True,
    ):
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

        Returns
        -------
        dict
            Retrieved evidence, context, resolution, and escalation state.
        """
        ticket_text = (ticket_text or "").strip()

        # --------------------------------------------------
        # VALIDATE TICKET
        # --------------------------------------------------
        if not ticket_text:
            return {
                "evidence": [],
                "context": "",
                "resolution": "",
                "requires_escalation": True,
                "status": "ESCALATED",
                "escalation_reason": "Insufficient Knowledge Base Coverage",
            }

        # --------------------------------------------------
        # STEP 1: KNOWLEDGE BASE RETRIEVAL
        # --------------------------------------------------
        evidence = self.retriever.search(
            query=ticket_text,
            category=category,
            top_k=top_k,
        )

        relevant_evidence = []
        for item in evidence or []:
            try:
                score = float(item.get("score", 0))
            except (TypeError, ValueError):
                score = 0.0
            if score >= MIN_RELEVANCE:
                relevant_evidence.append(item)

        if not relevant_evidence or not extract_steps(relevant_evidence):
            return {
                "evidence": relevant_evidence,
                "context": build_context(ticket_text, relevant_evidence),
                "resolution": "",
                "requires_escalation": True,
                "status": "ESCALATED",
                "escalation_reason": "Insufficient Knowledge Base Coverage",
            }

        if not generate_resolution:
            return {
                "evidence": relevant_evidence,
                "context": build_context(ticket_text, relevant_evidence),
                "resolution": "",
                "requires_escalation": False,
            }

        # --------------------------------------------------
        # STEP 2: CONTEXT AUGMENTATION + RESOLUTION
        # --------------------------------------------------
        # Pass the classifier's predicted category into the generator.
        # This keeps Operational Area tied to classification instead
        # of allowing retrieved KB evidence to replace it.
        response = generate_support_response(
            ticket_text=ticket_text,
            evidence=relevant_evidence,
            category=category,
        )

        resolution = str(response.get("resolution", "") or "").strip()
        if not resolution:
            return {
                "evidence": relevant_evidence,
                "context": response.get("context", ""),
                "resolution": "",
                "requires_escalation": True,
                "status": "ESCALATED",
                "escalation_reason": "Insufficient Knowledge Base Coverage",
            }

        # --------------------------------------------------
        # STEP 3: RETURN COMPLETE RESULT
        # --------------------------------------------------
        return {
            "evidence": relevant_evidence,
            "context": response.get("context", ""),
            "resolution": resolution,
            "requires_escalation": False,
        }


# ==========================================================
# SINGLE PIPELINE INSTANCE
# ==========================================================

_pipeline = None


# ==========================================================
# CONVENIENCE FUNCTION
# ==========================================================

def run_pipeline(
    ticket_text,
    category=None,
    top_k=3,
    generate_resolution=True,
):
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
