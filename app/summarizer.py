"""
Extractive summarization engine — pure Python, no external dependencies.

Algorithm
─────────
1. Split the transcript into sentences.
2. Build a normalized word-frequency table (stopwords excluded).
3. Score each sentence as the average frequency of its content words.
4. Return the top-N sentences in their original reading order.

Limitations (intentional — LLM integration can improve these later)
────────────────────────────────────────────────────────────────────
• Extractive only: returns existing sentences, never generates new text.
• English stopwords: scoring quality degrades for other languages.
• No semantic understanding: relies on term frequency, not meaning.
• Action/decision detection is pattern-based and may produce false positives.
• Unpunctuated Whisper output produces lower-quality splits; a word-count
  fallback is used when sentence-ending punctuation is sparse.
"""

import re
from collections import Counter


# ── Stop words ─────────────────────────────────────────────────────────────────

STOPWORDS = frozenset({
    # Articles / prepositions / conjunctions
    "a", "an", "the", "and", "or", "but", "nor", "so", "yet",
    "at", "by", "for", "from", "in", "into", "of", "off", "on", "onto",
    "out", "over", "past", "since", "to", "up", "upon", "with", "within",
    "without", "about", "above", "across", "after", "against", "along",
    "among", "around", "before", "behind", "below", "beneath", "beside",
    "between", "beyond", "down", "during", "except", "inside", "near",
    "outside", "through", "throughout", "under", "underneath", "until", "via",
    # Pronouns
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    # Auxiliary / modal verbs
    "be", "is", "am", "are", "was", "were", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "will", "would", "could", "should", "may", "might", "must", "shall", "can",
    # Common adverbs / adjectives / conjunctions
    "not", "no", "nor", "never", "always", "ever", "just", "also",
    "very", "too", "quite", "rather", "fairly", "enough",
    "here", "there", "when", "where", "why", "how",
    "all", "both", "each", "few", "more", "most", "other", "some", "such",
    "than", "then", "as", "if", "while", "although", "though",
    "because", "since", "unless", "until", "whereas",
    # Common transcript filler and function words
    "like", "um", "uh", "okay", "ok", "right", "yeah", "yes", "yep",
    "well", "now", "actually", "basically", "literally", "really",
    "kind", "sort", "way", "thing", "things", "stuff",
    "going", "get", "got", "getting", "make", "made", "making",
    "say", "said", "says", "saying",
    "know", "knew", "think", "thought", "thinking",
    "come", "came", "coming", "go", "went", "gone",
    "see", "saw", "seen", "look", "looked", "looking",
    "use", "used", "using", "want", "wanted", "let",
    "take", "took", "taking", "give", "gave", "given", "giving",
    "put", "mean", "means", "meant", "talk", "talked", "tell", "told",
    "ask", "asked",
    # Numbers and generic nouns
    "one", "two", "three", "four", "five",
    "first", "second", "third", "next", "last",
    "new", "old", "good", "great", "big", "small", "long", "little",
    "own", "same", "different", "much", "many", "every", "any",
    "back", "even", "still", "again", "already", "away",
    "time", "year", "day", "week", "month",
    "people", "person", "man", "men", "woman", "women",
})

# ── Pattern constants ──────────────────────────────────────────────────────────

_ACTION_RE = re.compile(
    r"\b("
    r"we should|we need to|we must|we will|you should|you need|"
    r"action item|follow.?up|next step|to.?do|deadline|"
    r"please \w+|let'?s \w+|i will|they will|someone will|"
    r"needs? to be|have to|going to \w+|"
    r"schedule|assign|complete|review|update|send|share|"
    r"implement|create|build|develop|fix|address|ensure"
    r")\b",
    re.IGNORECASE,
)

_DECISION_RE = re.compile(
    r"\b("
    r"decided|agreed|concluded|resolved|approved|confirmed|"
    r"the decision|final decision|consensus|we agreed|they agreed|"
    r"it was decided|it was agreed|we'?ve decided|going with|"
    r"chosen to|selected|will proceed|move forward"
    r")\b",
    re.IGNORECASE,
)

_EMPHATIC = frozenset({
    "important", "critical", "crucial", "key", "significant", "essential",
    "fundamental", "notable", "remarkable", "interesting", "fascinating",
    "surprising", "unexpected", "unique", "special", "major", "primary",
    "main", "central", "core", "vital", "necessary", "absolutely",
    "definitely", "certainly", "clearly", "obviously",
})


# ── Internal helpers ───────────────────────────────────────────────────────────

def _tokenize(text):
    return re.findall(r"\b[a-zA-Z]+\b", text.lower())


def _content_words(text):
    return [w for w in _tokenize(text) if w not in STOPWORDS and len(w) > 2]


def _build_freq(text):
    words = _content_words(text)
    if not words:
        return {}
    total = len(words)
    return {w: c / total for w, c in Counter(words).items()}


def _score(sentence, freq):
    words = _content_words(sentence)
    if not words:
        return 0.0
    return sum(freq.get(w, 0.0) for w in words) / len(words)


def _top_sentences(sentences, freq, n, exclude=None):
    """Return up to n best sentences in original order, skipping excluded indices."""
    skip = set(exclude or [])
    ranked = sorted(
        ((i, _score(s, freq), s) for i, s in enumerate(sentences) if i not in skip),
        key=lambda x: x[1],
        reverse=True,
    )
    chosen = sorted(ranked[:n], key=lambda x: x[0])  # restore reading order
    return [(i, s) for i, _, s in chosen]


# ── Public helpers ─────────────────────────────────────────────────────────────

def split_sentences(text):
    """
    Split text into sentences of at least 4 words.

    Falls back to fixed-word-count chunks when the transcript has too little
    punctuation (common with Whisper output on casual speech).
    """
    flat = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", flat)
    sentences = [p.strip() for p in parts if len(p.split()) >= 4]

    # Fallback: chunk by ~25 words when punctuation is sparse
    if len(sentences) < 5 and len(flat.split()) >= 40:
        words = flat.split()
        size = 25
        sentences = [
            " ".join(words[i : i + size])
            for i in range(0, len(words), size)
            if len(words[i : i + size]) >= 4
        ]
    return sentences


def extract_keywords(text, n=15):
    """Return the top n content words by frequency."""
    freq = _build_freq(text)
    return [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:n]]


# ── Main entry point ───────────────────────────────────────────────────────────

def summarize(text, n_summary=3, n_points=8, n_keywords=15):
    """
    Analyse the transcript and return a dict of extractive analysis results.

    No verbatim transcript text is returned — only selected sentences and
    keyword lists.  Callers that need the full text should keep their own copy.

    Returns
    ───────
    summary         str        Top sentences joined as a paragraph.
    key_points      list[str]  Next tier of high-scoring sentences.
    keywords        list[str]  Top content words by frequency.
    action_items    list[str]  Sentences matching action-word patterns.
    decisions       list[str]  Sentences matching decision patterns.
    notable_moments list[str]  Questions and sentences with emphatic words.
    study_questions list[str]  Real questions + keyword-based prompts.
    """
    text = text.strip()
    _empty = dict(
        summary="", key_points=[], keywords=[],
        action_items=[], decisions=[], notable_moments=[], study_questions=[],
    )
    if not text:
        return _empty

    sentences = split_sentences(text)
    if not sentences:
        return {**_empty, "summary": text[:500]}

    freq    = _build_freq(text)
    kws     = [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:n_keywords]]

    # Summary — scale count to text length; never more than 1 per 5 sentences
    n_sum  = min(n_summary, max(1, len(sentences) // 5))
    s_pairs = _top_sentences(sentences, freq, n=n_sum)
    s_idx   = {i for i, _ in s_pairs}
    summary = " ".join(s for _, s in s_pairs)

    # Key points — next tier, excluding summary sentences
    kp_pairs = _top_sentences(sentences, freq, n=n_points, exclude=s_idx)
    key_points = [s for _, s in kp_pairs]

    # Action items
    action_items = [s for s in sentences if _ACTION_RE.search(s)][:8]

    # Decisions
    decisions = [s for s in sentences if _DECISION_RE.search(s)][:6]

    # Notable moments — questions first, then emphatic sentences, then top-scored
    notable: list[str] = []
    seen: set[str] = set()
    for s in sentences:
        if s.strip().endswith("?"):
            notable.append(s)
            seen.add(s)
    for s in sentences:
        words_low = set(_tokenize(s))
        if words_low & _EMPHATIC and s not in seen:
            notable.append(s)
            seen.add(s)
    for _, s in _top_sentences(sentences, freq, n=10):
        if s not in seen:
            notable.append(s)
            seen.add(s)
        if len(notable) >= 6:
            break

    # Study questions — real questions + keyword-based prompts
    real_qs = [s for s in sentences if s.strip().endswith("?")]
    gen_qs  = [f"What is '{kw}' and why is it relevant here?" for kw in kws[:5]]
    study_questions = (real_qs + [q for q in gen_qs if q not in real_qs])[:6]

    return dict(
        summary=summary,
        key_points=key_points,
        keywords=kws,
        action_items=action_items,
        decisions=decisions,
        notable_moments=notable[:6],
        study_questions=study_questions,
    )
