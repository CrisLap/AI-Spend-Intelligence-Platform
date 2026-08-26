from __future__ import annotations

import json

from app.services.ai import chat
from app.services.cost_saving_agent import AGENT_TYPES
from app.services.guardrails import validate_input

_FORECAST_KEYWORDS = [
    "previsione", "prevedi", "forecast", "trend", "proietta", "proiezione",
    "prossimo mese", "next month", "andamento futuro",
]
_CONTRACT_RISK_KEYWORDS = [
    "rischio contrattuale", "rischi contrattuali", "clausola", "clausole",
    "penale", "penali", "rinnovo automatico", "esclusiva", "contract risk",
    "risky clause", "contratti in scadenza", "scadenza contratto", "tetto massimo",
]
_COST_SAVING_KEYWORDS = [
    "risparmi", "risparmio", "opportunità di risparmio", "riduci i costi",
    "ridurre i costi", "rinegozia", "rinegoziare", "ottimizza la spesa",
    "ottimizzazione", "taglia i costi", "cost saving", "save money",
    "reduce cost", "negotiate",
]
_CHAT_KEYWORDS = [
    "quanto abbiamo speso", "quanto abbiamo pagato", "quali fornitori",
    "mostrami", "elenca", "elenco", "che cosa", "cos'è", "come mai",
    "how much", "which supplier", "show me", "list all", "what is",
]

# Order matters: forecast/contract_risk/cost_saving are checked before the
# generic "chat" bucket, since a goal like "prevedi la spesa" would also
# contain no chat keywords but must not fall through to the default.
_LABEL_KEYWORDS = (
    ("forecast", _FORECAST_KEYWORDS),
    ("contract_risk", _CONTRACT_RISK_KEYWORDS),
    ("cost_saving", _COST_SAVING_KEYWORDS),
    ("chat", _CHAT_KEYWORDS),
)


def _rule_based(message: str) -> dict | None:
    ml = message.lower()
    best_label, best_hits = None, 0
    for label, keywords in _LABEL_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in ml)
        if hits > best_hits:
            best_label, best_hits = label, hits
    if best_label is None:
        return None
    confidence = min(0.95, 0.6 + 0.1 * best_hits)
    if best_label == "chat":
        return {"intent": "chat", "agent_type": None, "confidence": confidence, "method": "rule_based"}
    return {"intent": "cost_saving", "agent_type": best_label, "confidence": confidence, "method": "rule_based"}


_CLASSIFY_LLM_PROMPT = (
    "Classify the user message as either a spend-data QUESTION for a RAG "
    'chat assistant ("chat") or a GOAL for an autonomous cost-saving agent '
    '("cost_saving"). If it is a goal, also pick the best agent_type among '
    '"cost_saving" (find savings/renegotiation opportunities), "forecast" '
    '(project future spend) or "contract_risk" (find risky contract '
    "clauses). Reply ONLY with JSON: "
    '{{"intent": "chat" or "cost_saving", "agent_type": "cost_saving" or '
    '"forecast" or "contract_risk" or null}}. Message: "{message}"'
)


def _llm_based(message: str) -> dict | None:
    # Called before validate_input runs downstream in chat_react.py/
    # cost_saving_agent.py, so a message that guard would block still needs
    # a guard here - otherwise intent classification sends it to the LLM
    # unguarded regardless of what happens after routing.
    if validate_input(message) is not None:
        return None
    prompt = _CLASSIFY_LLM_PROMPT.format(message=message)
    try:
        result = chat([{"role": "user", "content": prompt}])
        parsed = json.loads(result)
        intent = parsed.get("intent")
        agent_type = parsed.get("agent_type")
        if intent == "chat":
            return {"intent": "chat", "agent_type": None, "confidence": 0.6, "method": "llm"}
        if intent == "cost_saving":
            if agent_type not in AGENT_TYPES:
                agent_type = "cost_saving"
            return {"intent": "cost_saving", "agent_type": agent_type, "confidence": 0.6, "method": "llm"}
    except Exception:
        pass
    return None


def classify_intent(message: str) -> dict:
    """Two-tier router: fast keyword rules first (deterministic, free, no
    network call), LLM fallback only when no keyword matched at all -
    mirrors the rule-then-LLM tiering already used for spend-description
    classification in classifier.py.

    Returns {"intent": "chat"|"cost_saving", "agent_type": str|None,
    "confidence": float, "method": str}.
    """
    rule = _rule_based(message)
    if rule:
        return rule
    llm = _llm_based(message)
    if llm:
        return llm
    # Default to "chat": a RAG answer degrades gracefully to "no relevant
    # data found" for an unmatched message, while routing it to the agent
    # would trigger a much slower multi-step ReAct run for what might just
    # be a greeting or an out-of-scope question.
    return {"intent": "chat", "agent_type": None, "confidence": 0.3, "method": "default"}
