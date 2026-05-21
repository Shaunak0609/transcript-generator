"""
Template-based note assembly built on top of the extractive summarizer.

Each template selects and labels a subset of the raw analysis to produce
output appropriate for the context (lecture, meeting, interview, podcast).

The returned dict always contains:
  "template"  str  — which template was used
  "layout"    list — ordered [(data_key, display_label, render_type), ...]
  + the data keys referenced in the layout

render_type values
──────────────────
  "text"         — paragraph of prose (used for summary)
  "list"         — bulleted list of sentences
  "keyword_list" — short terms displayed as a comma-separated line or inline list
"""

from app.summarizer import summarize

VALID_TEMPLATES = ("default", "lecture", "meeting", "interview", "podcast")

# Each template defines the sections it shows and how to label/render them.
# Order here is the display order in every output format.
_LAYOUT: dict[str, list[tuple[str, str, str]]] = {
    "default": [
        ("summary",    "Summary",    "text"),
        ("key_points", "Key Points", "list"),
        ("keywords",   "Key Terms",  "keyword_list"),
    ],
    "lecture": [
        ("summary",         "Summary",                  "text"),
        ("key_concepts",    "Key Concepts",             "keyword_list"),
        ("study_notes",     "Study Notes",              "list"),
        ("study_questions", "Possible Study Questions", "list"),
        ("keywords",        "Key Terms",                "keyword_list"),
    ],
    "meeting": [
        ("summary",      "Summary",               "text"),
        ("key_points",   "Key Points",            "list"),
        ("action_items", "Possible Action Items", "list"),
        ("decisions",    "Decisions Mentioned",   "list"),
        ("keywords",     "Key Terms",             "keyword_list"),
    ],
    "interview": [
        ("summary",         "Summary",         "text"),
        ("themes",          "Themes",          "keyword_list"),
        ("notable_moments", "Notable Moments", "list"),
        ("keywords",        "Key Terms",       "keyword_list"),
    ],
    "podcast": [
        ("summary",          "Episode Summary",  "text"),
        ("highlights",       "Highlights",       "list"),
        ("topics_discussed", "Topics Discussed", "keyword_list"),
        ("keywords",         "Key Terms",        "keyword_list"),
    ],
}


def generate(text, template="default", summary_only=False):
    """
    Analyse text with the extractive summarizer and return a structured
    notes dict shaped by the requested template.

    Parameters
    ──────────
    text         Full cleaned transcript text.
    template     One of VALID_TEMPLATES.  Unknown values fall back to "default".
    summary_only When True (--summary without --notes), only the summary
                 and keywords are returned using the "default" layout.

    Returns a dict with keys:  "template", "layout", plus all data keys
    referenced by the layout.  Empty sections (no matches found) are still
    present as empty lists/strings so exporters can detect and skip them.
    """
    template = template if template in VALID_TEMPLATES else "default"
    if summary_only:
        template = "default"

    raw = summarize(text)

    if template == "default" or summary_only:
        data = {
            "summary":    raw["summary"],
            "key_points": raw["key_points"][:6],
            "keywords":   raw["keywords"],
        }

    elif template == "lecture":
        data = {
            "summary":          raw["summary"],
            "key_concepts":     raw["keywords"][:10],      # top terms as concept list
            "study_notes":      raw["key_points"][:6],     # high-value sentences
            "study_questions":  raw["study_questions"],
            "keywords":         raw["keywords"],
        }

    elif template == "meeting":
        data = {
            "summary":      raw["summary"],
            "key_points":   raw["key_points"][:6],
            "action_items": raw["action_items"],
            "decisions":    raw["decisions"],
            "keywords":     raw["keywords"],
        }

    elif template == "interview":
        data = {
            "summary":          raw["summary"],
            "themes":           raw["keywords"][:8],       # top terms as theme labels
            "notable_moments":  raw["notable_moments"],
            "keywords":         raw["keywords"],
        }

    elif template == "podcast":
        data = {
            "summary":          raw["summary"],
            "highlights":       raw["notable_moments"][:5],
            "topics_discussed": raw["keywords"][:12],
            "keywords":         raw["keywords"],
        }

    else:
        data = {"summary": raw["summary"], "keywords": raw["keywords"]}

    return {"template": template, "layout": _LAYOUT[template], **data}
