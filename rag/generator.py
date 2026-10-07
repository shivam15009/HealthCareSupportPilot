"""
Healthcare Support Pilot
Milestone 2 - Resolution Generator

Generates structured operational troubleshooting responses using
retrieved knowledge-base evidence.

Safety scope:
- Healthcare operational support only
- IT/system troubleshooting only
- No diagnosis
- No disease prediction
- No treatment recommendations
- No medication recommendations
- No dosage advice
- No personalized medical advice

Resolution format:
1. Issue Summary
2. Operational Area
3. Recommended Troubleshooting Steps
4. Knowledge Sources
"""

MIN_RELEVANCE = 0.30
MAX_STEPS = 5


def clean_text(value):
    """Normalize a value for safe display."""
    if value is None:
        return ""

    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value)

    text = str(value).strip()
    return " ".join(text.split()) if text else ""


def build_context(ticket_text, evidence):
    """
    Build context for the resolution stage.

    The original ticket is kept as the primary issue description.
    Retrieved evidence is included with relevance and source metadata.
    """
    context_parts = [
        "SUPPORT TICKET",
        clean_text(ticket_text),
        "",
        "RETRIEVED KNOWLEDGE-BASE EVIDENCE",
    ]

    if not evidence:
        context_parts.append(
            "No relevant knowledge-base evidence was found."
        )
        return "\n".join(context_parts)

    for index, item in enumerate(evidence, start=1):
        resolution = item.get("resolution", "")
        if isinstance(resolution, list):
            resolution = " ".join(
                clean_text(step) for step in resolution if clean_text(step)
            )

        context_parts.extend(
            [
                "",
                f"Evidence {index}",
                f"Title: {clean_text(item.get('title', ''))}",
                f"Category: {clean_text(item.get('category', ''))}",
                f"Knowledge Base Type: {clean_text(item.get('kb_type', ''))}",
                f"Relevance Score: {item.get('score', 0)}",
                f"Issue: {clean_text(item.get('issue', ''))}",
                f"Resolution: {clean_text(resolution)}",
                f"Source: {clean_text(item.get('source_title', ''))}",
                f"Source URL: {clean_text(item.get('source_url', ''))}",
            ]
        )

    return "\n".join(context_parts)


def _normalize_step(value):
    """Normalize a troubleshooting step for duplicate comparison."""
    return " ".join(clean_text(value).lower().strip(" .:-").split())


def _split_string_resolution(resolution):
    """
    Split a string resolution only when it clearly contains
    separate actionable instructions.

    A single sentence is preserved as one step.
    """
    text = clean_text(resolution)
    if not text:
        return []

    # Numbered procedures such as "1. Check ... 2. Restart ..."
    numbered_parts = []
    current = []
    for part in text.replace("\r", " ").split():
        if part.endswith(".") and part[:-1].isdigit():
            if current:
                numbered_parts.append(" ".join(current))
                current = []
        else:
            current.append(part)

    if numbered_parts:
        if current:
            numbered_parts.append(" ".join(current))
        return [clean_text(part) for part in numbered_parts if clean_text(part)]

    # Semicolons are a strong signal that a KB record contains
    # multiple independent actions.
    if ";" in text:
        return [clean_text(part) for part in text.split(";") if clean_text(part)]

    # Preserve a normal sentence as one step. Only split when there
    # are multiple clear sentences, avoiding arbitrary fragments.
    sentences = []
    buffer = []
    for character in text:
        buffer.append(character)
        if character in ".!?":
            sentence = clean_text("".join(buffer))
            if sentence:
                sentences.append(sentence)
            buffer = []

    remainder = clean_text("".join(buffer))
    if remainder:
        sentences.append(remainder)

    if len(sentences) > 1:
        return sentences

    return [text]


def _resolution_steps(resolution):
    """Return ordered actionable steps from a KB resolution value."""
    if isinstance(resolution, (list, tuple)):
        steps = []
        for item in resolution:
            if isinstance(item, (list, tuple)):
                steps.extend(_resolution_steps(item))
            else:
                text = clean_text(item)
                if text:
                    steps.append(text)
        return steps

    return _split_string_resolution(resolution)


def extract_steps(evidence):
    """
    Extract ordered troubleshooting steps from retrieved KB evidence.

    The generator does not invent actions. It only reorganizes
    troubleshooting actions already present in the retrieved evidence.
    """
    steps = []
    seen = set()

    for item in evidence:
        for step in _resolution_steps(item.get("resolution", "")):
            normalized = _normalize_step(step)

            if not normalized or normalized in seen:
                continue

            seen.add(normalized)
            steps.append(step)

            if len(steps) >= MAX_STEPS:
                return steps

    return steps


def _valid_evidence(evidence):
    """Keep only evidence meeting the configured relevance threshold."""
    valid = []

    for item in evidence or []:
        try:
            score = float(item.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0

        if score >= MIN_RELEVANCE:
            valid.append(item)

    return valid


def _format_score(item):
    """Format an evidence score for display."""
    try:
        return f"{float(item.get('score', 0)) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def generate_resolution(ticket_text, evidence, category=None):
    """
    Generate a structured operational troubleshooting response.

    The issue summary comes from the original ticket, not from a
    retrieved KB issue. Troubleshooting steps come only from relevant
    KB evidence.
    """
    ticket_text = clean_text(ticket_text)

    if not ticket_text:
        return "No support ticket description was provided."

    valid_evidence = _valid_evidence(evidence)

    if not valid_evidence:
        return (
            "No sufficiently relevant knowledge-base evidence was found "
            "for this ticket."
        )

    steps = extract_steps(valid_evidence)

    if not steps:
        return (
            "No sufficiently relevant knowledge-base evidence was found "
            "for this ticket."
        )

    # `category` is intended to receive the classifier's predicted
    # operational category. When it is not supplied, use the best
    # retrieved evidence as a compatibility fallback.
    operational_area = clean_text(category)
    if not operational_area:
        operational_area = clean_text(
            valid_evidence[0].get("category", "")
        )

    if not operational_area:
        operational_area = "Operational Support"

    response_parts = [
        "AI Operational Resolution",
        "",
        "Issue Summary",
        ticket_text,
        "",
        "Operational Area",
        operational_area,
        "",
        "Recommended Troubleshooting Steps",
    ]

    for index, step in enumerate(steps, start=1):
        response_parts.append(f"{index}. {step}")

    response_parts.extend(
        [
            "",
            "Knowledge Sources",
        ]
    )

    for index, item in enumerate(valid_evidence, start=1):
        source_title = clean_text(item.get("source_title", ""))
        source_url = clean_text(item.get("source_url", ""))
        kb_title = clean_text(item.get("title", ""))

        if not source_title:
            source_title = "Knowledge Base Source"

        source_line = f"{index}. {source_title}"

        if kb_title:
            source_line += f" — {kb_title}"

        source_line += f" (Relevance: {_format_score(item)})"
        response_parts.append(source_line)

        if source_url:
            response_parts.append(f"   Source URL: {source_url}")

    return "\n".join(response_parts)


def generate_support_response(ticket_text, evidence, category=None):
    """
    Main generator interface.

    Returns:
        {
            "context": "...",
            "resolution": "..."
        }
    """
    context = build_context(ticket_text, evidence)
    resolution = generate_resolution(
        ticket_text=ticket_text,
        evidence=evidence,
        category=category,
    )

    return {
        "context": context,
        "resolution": resolution,
    }
