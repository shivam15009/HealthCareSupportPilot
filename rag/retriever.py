"""
Healthcare Support Pilot
Milestone 2 - Knowledge Retrieval

Improved local TF-IDF knowledge-base retriever.

Retrieval strategy:
Support Ticket
      ↓
Word TF-IDF similarity
      +
Character TF-IDF similarity
      +
Category relevance
      +
Knowledge-base keyword overlap
      ↓
Duplicate filtering
      ↓
Minimum relevance filtering
      ↓
Top-K knowledge-base evidence

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

import json
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# CONFIGURATION
# ============================================================

MIN_RELEVANCE = 0.30
DEFAULT_TOP_K = 3

CATEGORY_BONUS = 0.12
KEYWORD_BONUS = 0.10

WORD_WEIGHT = 0.75
CHARACTER_WEIGHT = 0.25

MAX_TOP_K = 10


# ============================================================
# OPERATIONAL CONCEPTS
# ============================================================

OPERATIONAL_KEYWORDS = {
    "printer": {
        "printer",
        "printing",
        "print",
        "printer queue",
        "print queue",
        "print job",
        "document printing",
        "printer error",
        "offline printer",
    },
    "scanner": {
        "scanner",
        "scanning",
        "scan",
        "document scanner",
    },
    "network": {
        "network",
        "connectivity",
        "connection",
        "internet",
        "ethernet",
        "wifi",
        "wi-fi",
        "wireless",
        "outage",
        "timeout",
    },
    "login": {
        "login",
        "log in",
        "authentication",
        "authenticate",
        "password",
        "username",
        "access",
        "account",
        "permission",
        "smartcard",
    },
    "laboratory": {
        "laboratory",
        "lab",
        "lab workstation",
        "lab system",
        "lab portal",
        "laboratory system",
    },
    "pharmacy": {
        "pharmacy",
        "dispensing",
        "dispensing system",
        "pharmacy system",
        "prescription",
    },
    "billing": {
        "billing",
        "invoice",
        "payment",
        "insurance",
        "financial",
        "claim",
    },
    "appointment": {
        "appointment",
        "booking",
        "scheduling",
        "schedule",
        "referral",
    },
    "registration": {
        "registration",
        "patient registration",
        "intake",
        "patient intake",
    },
    "equipment": {
        "equipment",
        "device",
        "workstation",
        "hardware",
        "maintenance",
    },
}


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    """Normalize text for matching and duplicate comparison."""

    if text is None:
        return ""

    if isinstance(text, list):
        text = " ".join(str(item) for item in text)

    text = str(text).lower()

    # Keep letters, numbers, and hyphens.
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def tokenize(text):
    """Return normalized word tokens."""

    normalized = normalize_text(text)

    if not normalized:
        return set()

    return set(normalized.split())


# ============================================================
# KEYWORD / CONCEPT MATCHING
# ============================================================

def detect_operational_concepts(text):
    """
    Detect operational concepts using word/phrase boundaries.

    This avoids substring errors such as matching "scan" inside
    an unrelated word.
    """

    normalized = normalize_text(text)
    concepts = set()

    if not normalized:
        return concepts

    for concept, keywords in OPERATIONAL_KEYWORDS.items():
        for keyword in keywords:
            keyword_normalized = normalize_text(keyword)

            if not keyword_normalized:
                continue

            pattern = (
                r"(?<!\w)"
                + re.escape(keyword_normalized)
                + r"(?!\w)"
            )

            if re.search(pattern, normalized):
                concepts.add(concept)
                break

    return concepts


def extract_document_keywords(document):
    """
    Read explicit keywords from the new KB schema.

    The function also supports older KB records that do not contain
    a keywords field.
    """

    keywords = document.get("keywords", [])

    if isinstance(keywords, str):
        keywords = [keywords]

    if not isinstance(keywords, list):
        keywords = []

    return {
        normalize_text(keyword)
        for keyword in keywords
        if normalize_text(keyword)
    }


def calculate_keyword_score(query, document):
    """
    Calculate keyword/concept overlap.

    Explicit KB keywords receive priority. Operational concepts are
    used as a fallback/secondary signal so tickets such as
    "printer is not printing" match printer-related entries even
    when wording differs.
    """

    query_normalized = normalize_text(query)

    if not query_normalized:
        return 0.0

    query_tokens = tokenize(query_normalized)
    query_concepts = detect_operational_concepts(query_normalized)

    document_keywords = extract_document_keywords(document)

    document_text = build_document_text(document)
    document_tokens = tokenize(document_text)
    document_concepts = detect_operational_concepts(document_text)

    explicit_matches = 0

    for keyword in document_keywords:
        if not keyword:
            continue

        if " " in keyword:
            if re.search(
                r"(?<!\w)" + re.escape(keyword) + r"(?!\w)",
                query_normalized,
            ):
                explicit_matches += 1
        elif keyword in query_tokens:
            explicit_matches += 1

    explicit_score = 0.0

    if document_keywords:
        explicit_score = min(
            explicit_matches / len(document_keywords),
            1.0,
        )

    concept_overlap = query_concepts.intersection(
        document_concepts
    )

    concept_score = 0.0

    if query_concepts:
        concept_score = (
            len(concept_overlap)
            / len(query_concepts)
        )

    # Also reward exact ticket terms occurring in the document.
    # This is intentionally capped so TF-IDF remains the main signal.
    token_overlap = 0.0

    if query_tokens:
        token_overlap = len(
            query_tokens.intersection(document_tokens)
        ) / len(query_tokens)

    return min(
        (0.55 * explicit_score)
        + (0.30 * concept_score)
        + (0.15 * token_overlap),
        1.0,
    )


# ============================================================
# DUPLICATE SIGNATURE
# ============================================================

def clean_variant_text(text):
    """
    Remove legacy Variant XX labels so old synthetic KB variants
    do not occupy multiple result slots.
    """

    normalized = normalize_text(text)

    normalized = re.sub(
        r"\bvariant\s+\d+\b",
        "",
        normalized,
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized.strip()


def build_duplicate_signature(document):
    """
    Create a normalized identity for an operational KB entry.

    Prefer issue + category + normalized resolution rather than
    the KB title alone. This prevents near-identical records from
    filling all top-K evidence slots.
    """

    category = clean_variant_text(
        document.get("category", "")
    )

    issue = clean_variant_text(
        document.get("issue", "")
    )

    resolution = document.get("resolution", "")

    if isinstance(resolution, list):
        resolution = " ".join(
            str(step) for step in resolution
        )

    resolution = clean_variant_text(resolution)

    # Keep the signature compact while retaining enough information
    # to distinguish genuinely different procedures.
    return (
        category,
        issue,
        resolution[:300],
    )


# ============================================================
# DOCUMENT TEXT
# ============================================================

def build_document_text(document):
    """
    Build the searchable representation of a KB document.

    The new schema's keywords are deliberately included because
    they are curated retrieval signals.
    """

    resolution = document.get("resolution", "")

    if isinstance(resolution, list):
        resolution = " ".join(
            str(step) for step in resolution
        )

    keywords = document.get("keywords", [])

    if isinstance(keywords, list):
        keywords = " ".join(
            str(keyword) for keyword in keywords
        )

    text_parts = [
        document.get("title", ""),
        document.get("issue", ""),
        keywords,
        resolution,
        document.get("verification", ""),
        document.get("category", ""),
        document.get("kb_type", ""),
        document.get("source_title", ""),
        document.get("source_note", ""),
    ]

    return " ".join(
        str(part)
        for part in text_parts
        if part
    )


# ============================================================
# KNOWLEDGE RETRIEVER
# ============================================================

class KnowledgeRetriever:

    def __init__(self):

        base_dir = (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )

        json_path = (
            base_dir
            / "data"
            / "knowledge_base.json"
        )

        if not json_path.exists():
            raise FileNotFoundError(
                "\nKnowledge Base JSON not found.\n"
                f"Expected:\n{json_path}\n"
            )

        with open(
            json_path,
            "r",
            encoding="utf-8",
        ) as file:
            self.documents = json.load(file)

        if not self.documents:
            raise ValueError(
                "Knowledge Base JSON is empty."
            )

        if not isinstance(
            self.documents,
            list,
        ):
            raise ValueError(
                "Knowledge Base JSON must contain "
                "a list of documents."
            )

        self.texts = [
            build_document_text(document)
            for document in self.documents
        ]

        # --------------------------------------------------------
        # Word TF-IDF
        # --------------------------------------------------------

        self.word_vectorizer = TfidfVectorizer(
            stop_words="english",
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )

        self.word_vectors = (
            self.word_vectorizer.fit_transform(
                self.texts
            )
        )

        # --------------------------------------------------------
        # Character TF-IDF
        # --------------------------------------------------------

        self.character_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            lowercase=True,
            ngram_range=(3, 5),
            min_df=1,
            sublinear_tf=True,
        )

        self.character_vectors = (
            self.character_vectorizer.fit_transform(
                self.texts
            )
        )

        print(
            "Knowledge Base loaded: "
            f"{len(self.documents)} documents"
        )

    # ========================================================
    # SEARCH
    # ========================================================

    def search(
        self,
        query,
        category=None,
        top_k=DEFAULT_TOP_K,
    ):
        """Return the highest-quality relevant KB evidence."""

        if not query:
            return []

        query = str(query).strip()

        if not query:
            return []

        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            top_k = DEFAULT_TOP_K

        top_k = max(
            1,
            min(top_k, MAX_TOP_K),
        )

        # ----------------------------------------------------
        # Query vectors
        # ----------------------------------------------------

        query_word_vector = (
            self.word_vectorizer.transform([query])
        )

        query_character_vector = (
            self.character_vectorizer.transform([query])
        )

        word_scores = cosine_similarity(
            query_word_vector,
            self.word_vectors,
        )[0]

        character_scores = cosine_similarity(
            query_character_vector,
            self.character_vectors,
        )[0]

        requested_category = normalize_text(
            category
        )

        candidates = []

        # ----------------------------------------------------
        # Score every document
        # ----------------------------------------------------

        for index, document in enumerate(
            self.documents
        ):

            word_score = float(
                word_scores[index]
            )

            character_score = float(
                character_scores[index]
            )

            base_score = (
                WORD_WEIGHT * word_score
                + CHARACTER_WEIGHT * character_score
            )

            document_category = normalize_text(
                document.get("category", "")
            )

            category_bonus = 0.0

            if (
                requested_category
                and document_category
                == requested_category
            ):
                category_bonus = CATEGORY_BONUS

            keyword_score = calculate_keyword_score(
                query,
                document,
            )

            keyword_bonus = (
                KEYWORD_BONUS * keyword_score
            )

            final_score = min(
                base_score
                + category_bonus
                + keyword_bonus,
                1.0,
            )

            # ------------------------------------------------
            # Minimum relevance
            #
            # Require the actual semantic TF-IDF signal to
            # contribute. Category/keyword bonuses alone must
            # never make an unrelated document pass.
            # ------------------------------------------------

            if (
                base_score < 0.20
                and keyword_score < 0.35
            ):
                continue

            if final_score < MIN_RELEVANCE:
                continue

            candidates.append({
                "index": index,
                "score": final_score,
                "base_score": base_score,
                "word_score": word_score,
                "character_score": character_score,
                "keyword_score": keyword_score,
                "category_bonus": category_bonus,
            })

        # ----------------------------------------------------
        # Sort candidates
        # ----------------------------------------------------

        candidates.sort(
            key=lambda item: (
                item["score"],
                item["keyword_score"],
                item["base_score"],
            ),
            reverse=True,
        )

        # ----------------------------------------------------
        # Remove duplicate / near-duplicate records
        # ----------------------------------------------------

        results = []
        seen_signatures = set()

        for candidate in candidates:

            index = candidate["index"]
            document = self.documents[index]

            signature = build_duplicate_signature(
                document
            )

            if signature in seen_signatures:
                continue

            seen_signatures.add(signature)

            resolution = document.get(
                "resolution",
                [],
            )

            if isinstance(resolution, str):
                resolution = [resolution]

            results.append({
                "kb_id": document.get("kb_id"),
                "title": document.get("title"),
                "category": document.get("category"),
                "kb_type": document.get("kb_type"),
                "issue": document.get("issue"),
                "keywords": document.get("keywords", []),
                "resolution": resolution,
                "verification": document.get(
                    "verification",
                    "",
                ),
                "score": round(
                    candidate["score"],
                    4,
                ),
                "source_title": document.get(
                    "source_title"
                ),
                "source_url": document.get(
                    "source_url"
                ),
                "source_type": document.get(
                    "source_type"
                ),
                "source_note": document.get(
                    "source_note"
                ),
            })

            if len(results) >= top_k:
                break

        return results
