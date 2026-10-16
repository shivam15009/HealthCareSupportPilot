
from rag.retriever import KnowledgeRetriever
from rag.generator import generate_support_response


class SupportPipeline:
    """Run the complete local RAG workflow."""

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
        Retrieve knowledge and optionally generate a resolution.

        Parameters
        ----------
        ticket_text : str
            Original support ticket description.

        category : str, optional
            Category predicted by the ticket classifier.

        top_k : int
            Maximum number of knowledge records to retrieve.

        generate_resolution : bool
            Whether to generate troubleshooting instructions.

        Returns
        -------
        dict
            Evidence, context, resolution, and escalation information.
        """

        ticket_text = (ticket_text or "").strip()

        # --------------------------------------------------
        # STEP 1: VALIDATE THE TICKET
        # --------------------------------------------------
        if not ticket_text:
            return {
                "evidence": [],
                "context": "",
                "resolution": (
                    "No support ticket description was provided."
                ),
                "requires_escalation": True,
            }

        # --------------------------------------------------
        # STEP 2: RETRIEVE RELEVANT KNOWLEDGE
        # --------------------------------------------------
        evidence = self.retriever.search(
            query=ticket_text,
            category=category,
            top_k=top_k,
        )

        # --------------------------------------------------
        # STEP 3: CHECK KNOWLEDGE AVAILABILITY
        # --------------------------------------------------
        if not evidence:
            return {
                "evidence": [],
                "context": "",
                "resolution": (
                    "No sufficiently relevant knowledge-base "
                    "evidence was found for this ticket."
                ) if generate_resolution else "",
                "requires_escalation": True,
            }

        # --------------------------------------------------
        # STEP 4: GENERATE OPERATIONAL RESOLUTION
        # --------------------------------------------------
        if generate_resolution:
            response = generate_support_response(
                ticket_text=ticket_text,
                evidence=evidence,
                category=category,
            )

            context = response.get("context", "")
            resolution = response.get("resolution", "")

            # A resolution must contain usable troubleshooting
            # instructions. Evidence alone is not sufficient.
            requires_escalation = not bool(
                str(resolution or "").strip()
                and "No sufficiently relevant knowledge-base evidence"
                not in str(resolution)
            )

        else:
            # Human review is required, so skip resolution
            # generation while retaining retrieved evidence.
            context = ""
            resolution = ""
            requires_escalation = False

        # --------------------------------------------------
        # STEP 5: RETURN RESULTS
        # --------------------------------------------------
        return {
            "evidence": evidence,
            "context": context,
            "resolution": resolution,
            "requires_escalation": requires_escalation,
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
    Run the RAG pipeline.

    Example
    -------
    result = run_pipeline(
        ticket_text="The laboratory system is not syncing results",
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
