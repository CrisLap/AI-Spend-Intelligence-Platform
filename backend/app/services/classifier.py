from __future__ import annotations

from app.services.ai import chat, cosine_similarity, embed_text

UNSPSC_TAXONOMY: dict[str, list[str]] = {
    "Office Equipment & Supplies": ["toner", "cartridge", "paper", "pen", "stationery", "printer", "stapler"],
    "Computer Equipment & Accessories": ["laptop", "notebook", "monitor", "server", "workstation", "computer", "pc"],
    "Networking Equipment": ["router", "switch", "access point", "network cable", "firewall", "modem"],
    "Software & Digital Licenses": ["license", "subscription", "saas", "software", "cloud"],
    "Building & Facility Maintenance": ["cleaning", "maintenance", "hvac", "plumbing", "electrician"],
    "Professional & Consulting Services": ["consulting", "legal", "audit", "advisory", "notary"],
    "Travel & Transportation": ["flight", "hotel", "taxi", "train", "shipping", "courier"],
    "Raw Materials & Components": ["steel", "resin", "plastic", "aluminum", "component", "raw material"],
    "Utilities & Energy": ["gas", "water", "electricity", "utility"],
    "Medical & Healthcare": ["pharmaceutical", "medical", "gloves", "mask", "sanitary"],
    "Marketing & Advertising": ["advertising", "marketing", "social media", "seo", "campaign"],
    "Furniture & Furnishings": ["desk", "chair", "cabinet", "table", "furniture"],
    "HR & Personnel Services": ["training", "recruitment", "personnel", "payroll", "hr"],
}

# Real UNSPSC segment/family codes (the granularity that best fits these
# broad spend categories), verified against the public UNSPSC codeset.
UNSPSC_CODES: dict[str, str] = {
    "Office Equipment & Supplies": "44120000",  # Family: Office supplies
    "Computer Equipment & Accessories": "43210000",  # Family: Computer Equipment and Accessories
    "Networking Equipment": "43220000",  # Family: Data Voice or Multimedia Network Equipment or Platforms and Accessories
    "Software & Digital Licenses": "43230000",  # Family: Software
    "Building & Facility Maintenance": "72000000",  # Segment: Building and Facility Construction and Maintenance Services
    "Professional & Consulting Services": "80000000",  # Segment: Management and Business Professionals and Administrative Services
    "Travel & Transportation": "90000000",  # Segment: Travel and Food and Lodging and Entertainment Services
    "Raw Materials & Components": "11000000",  # Segment: Mineral and Textile and Inedible Plant and Animal Materials
    "Utilities & Energy": "83000000",  # Segment: Public Utilities and Public Sector Related Services
    "Medical & Healthcare": "42000000",  # Segment: Medical Equipment and Accessories and Supplies
    "Marketing & Advertising": "80140000",  # Family: Sales and business promotion activities
    "Furniture & Furnishings": "56000000",  # Segment: Furniture and Furnishings
    "HR & Personnel Services": "80110000",  # Family: Human resources services
}

_CATEGORY_EXEMPLARS = {c: f"{c}: " + ", ".join(kws) for c, kws in UNSPSC_TAXONOMY.items()}

# Feedback-based exemplars are scoped by role, not just category: a buyer's
# correction should improve classification for the buyer pool only, not
# leak into finance's (or vice versa), mirroring the same role-based
# visibility boundary applied to documents/line items elsewhere. Keyed by
# (role, category); role is resolved by the caller as "whichever pool this
# document/line item belongs to" - see classification.py and
# feedback_service.py for how that role is determined per call site.
_ROLES = ("buyer", "finance", "admin")
_FEEDBACK_EXEMPLARS: dict[tuple[str, str], list[str]] = {
    (role, c): [] for role in _ROLES for c in UNSPSC_TAXONOMY
}


def seed_feedback_exemplars(feedback_items: list[tuple[str, str, str]]) -> None:
    """feedback_items is a list of (description, corrected_category, role)."""
    for desc, corrected_cat, role in feedback_items:
        key = (role, corrected_cat)
        if key in _FEEDBACK_EXEMPLARS and desc not in _FEEDBACK_EXEMPLARS[key]:
            _FEEDBACK_EXEMPLARS[key].append(desc)


def _rule_based(desc: str) -> tuple[str, float] | None:
    dl = desc.lower()
    best_cat, best_hits = None, 0
    for cat, kws in UNSPSC_TAXONOMY.items():
        hits = sum(1 for kw in kws if kw in dl)
        if hits > best_hits:
            best_hits, best_cat = hits, cat
    if best_cat is None:
        return None
    return best_cat, min(0.99, 0.75 + 0.08 * best_hits)


def _embedding_based_with_feedback(desc: str, role: str) -> tuple[str, float]:
    vec = embed_text(desc)
    cats = list(_CATEGORY_EXEMPLARS.keys())

    base_sims = [cosine_similarity(vec, embed_text(_CATEGORY_EXEMPLARS[c])) for c in cats]

    fb_sims = [0.0] * len(cats)
    for i, cat in enumerate(cats):
        fb_descs = _FEEDBACK_EXEMPLARS.get((role, cat), [])
        if fb_descs:
            fb_vecs = [embed_text(fb) for fb in fb_descs if fb]
            if fb_vecs:
                fb_sims[i] = sum(cosine_similarity(vec, fv) for fv in fb_vecs) / len(fb_vecs)

    combined = [max(base_sims[i], fb_sims[i] * 0.9) for i in range(len(cats))]
    best_i = max(range(len(combined)), key=lambda i: combined[i])
    confidence = max(0.30, min(0.95, combined[best_i]))
    return cats[best_i], confidence


_FEEDBACK_SIM_THRESHOLD = 0.85


def _feedback_based(desc: str, role: str) -> tuple[str, float] | None:
    """Check for a previously user-corrected description (within this
    role's pool) close enough to override the classification, including a
    rule-based keyword match.

    Without this, corrections only ever get consulted inside
    _embedding_based_with_feedback, which is reached only when
    _rule_based finds no keyword at all - so any description containing a
    taxonomy keyword would keep re-triggering the same mistake forever,
    no matter how many times a user corrected it.
    """
    role_exemplars = {cat: descs for (r, cat), descs in _FEEDBACK_EXEMPLARS.items() if r == role}
    if not any(role_exemplars.values()):
        return None
    vec = embed_text(desc)
    best_cat, best_sim = None, 0.0
    for cat, fb_descs in role_exemplars.items():
        for fb in fb_descs:
            if not fb:
                continue
            sim = cosine_similarity(vec, embed_text(fb))
            if sim > best_sim:
                best_sim, best_cat = sim, cat
    if best_cat is not None and best_sim >= _FEEDBACK_SIM_THRESHOLD:
        return best_cat, min(0.95, best_sim)
    return None


_CLASSIFY_LLM_PROMPT = (
    "Classify the following spend description into one of the UNSPSC-like categories: "
    "{categories}. "
    "Reply ONLY with the exact category name and confidence (0-1) as JSON: "
    '{{"category": "...", "confidence": 0.0}}. Description: "{desc}"'
)


def _llm_based(desc: str) -> tuple[str, float] | None:
    cats = list(UNSPSC_TAXONOMY.keys())
    prompt = _CLASSIFY_LLM_PROMPT.format(categories=", ".join(cats), desc=desc)
    try:
        result = chat([{"role": "user", "content": prompt}])
        import json
        parsed = json.loads(result)
        cat = parsed.get("category", "")
        conf = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
        if cat in cats:
            return cat, conf
    except Exception:
        pass
    return None


def classify_description(desc: str, role: str = "buyer") -> dict:
    """role selects which pool's feedback exemplars to consult - the pool
    the description's document belongs to (see classification.py/
    feedback_service.py for how callers resolve it). Defaults to "buyer"
    for callers that don't have a role in scope (e.g. standalone scripts)."""
    feedback = _feedback_based(desc, role)
    if feedback:
        cat, conf = feedback
        return {"description": desc, "category": cat, "unspsc": UNSPSC_CODES.get(cat, ""), "confidence": conf, "method": "feedback"}
    rule = _rule_based(desc)
    if rule:
        cat, conf = rule
        return {"description": desc, "category": cat, "unspsc": UNSPSC_CODES.get(cat, ""), "confidence": conf, "method": "rule_based"}
    emb = _embedding_based_with_feedback(desc, role)
    cat, conf = emb
    llm = _llm_based(desc)
    if llm and llm[1] > conf:
        cat, conf = llm
        return {"description": desc, "category": cat, "unspsc": UNSPSC_CODES.get(cat, ""), "confidence": conf, "method": "llm"}
    return {"description": desc, "category": cat, "unspsc": UNSPSC_CODES.get(cat, ""), "confidence": conf, "method": "embedding"}


def classify_batch(descriptions: list[str], role: str = "buyer") -> list[dict]:
    return [classify_description(d, role) for d in descriptions]

