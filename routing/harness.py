"""Five routing arms, one interface: decide(scenario) -> Decision."""
import json, os, re, time
from dataclasses import dataclass, field

TOOLS = ["authenticate_customer","get_account_summary","get_billing_history","dispute_charge",
         "issue_refund","check_outage_status","run_line_diagnostics","schedule_technician",
         "change_plan","cancel_service","report_fraud","transfer_to_human"]
SPEC = open(os.path.join(os.path.dirname(__file__), "tools.md")).read()
LLM_MODEL = os.environ.get("ROUTE_LLM_MODEL", "gpt-4.1-mini")
LLM_PRICES = {"gpt-4.1-mini": (0.40, 1.60), "gpt-4.1": (2.00, 8.00)}

INTENTS = {
    "account_info":   "Asking about their plan, balance or account status.",
    "billing_detail": "Asking about a specific charge, invoice or refund.",
    "service_problem":"Reporting that their service or equipment is not working properly.",
    "plan_change":    "Asking to change, upgrade or downgrade the subscription.",
    "cancellation":   "Asking to end the service.",
    "fraud":          "Reporting unauthorized access or activity on the account.",
    "human":          "Asking to speak to a person.",
    "other":          "Something none of the above covers.",
}
QUESTIONS = {
    "requests_human":      "The caller explicitly asks to speak to a person, supervisor, manager or representative.",
    "unauthorized_access": "The caller suggests somebody who is not an authorized user of the account accessed or used it.",
    "needs_account_data":  "Answering the caller requires data specific to their account, or changes something on it.",
    "charge_identified":   "A specific individual charge has already been named or surfaced in this conversation.",
    "error_established":   "It has already been established, here or in the account notes, that a charge was billed in error.",
    "service_problem":     "The caller is reporting that their service or equipment is not working properly.",
    "intends_to_cancel":   "The caller states a clear intention to cancel. A conditional threat or a complaint is not an intention.",
}

@dataclass
class Decision:
    tool: str
    latency_ms: float
    sem: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    raw: str = ""

def render(sc):
    a = sc["account"]
    convo = "\n".join(f"{t['role'].upper()}: {t['text']}" for t in sc["transcript"])
    notes = "\n".join(f"  - {n}" for n in a["notes"]) or "  (none)"
    return (f"CONVERSATION\n{convo}\n\nCALLER STATE\n"
            f"  authenticated: {a['authenticated']}\n"
            f"  outage_already_checked: {a['outage_checked']}\n"
            f"  diagnostics_already_run: {a['diagnostics_run']}\n"
            f"ACCOUNT NOTES\n{notes}")

def route(sc, sem, intent, T=0.5):
    """The routing rules from tools.md, in order, as code."""
    a = sc["account"]
    if sem.get("requests_human", 0) >= T: return "transfer_to_human"          # R1
    if sem.get("unauthorized_access", 0) >= T: return "report_fraud"          # R2
    if not a["authenticated"] and sem.get("needs_account_data", 0) >= T:
        return "authenticate_customer"                                        # R3
    if intent == "human": return "transfer_to_human"
    if intent == "fraud": return "report_fraud"
    if intent == "service_problem" or sem.get("service_problem", 0) >= T:     # R6
        if not a["outage_checked"]: return "check_outage_status"
        if not a["diagnostics_run"]: return "run_line_diagnostics"
        return "schedule_technician"
    if intent == "billing_detail":
        if sem.get("error_established", 0) >= T: return "issue_refund"        # R5
        if sem.get("charge_identified", 0) >= T: return "dispute_charge"      # R4
        return "get_billing_history"
    if intent == "cancellation":
        return "cancel_service" if sem.get("intends_to_cancel", 0) >= T else "get_account_summary"  # R8
    if intent == "plan_change": return "change_plan"
    if intent == "account_info": return "get_account_summary"
    return "transfer_to_human"

# ------------------------------------------------- arm A: naive keyword router
KEYS = [("supervisor|manager|human|a person|representative", "transfer_to_human"),
        ("fraud|wasn't me|was not me|stolen|hacked|unauthorized", "report_fraud"),
        ("cancel", "cancel_service"),
        ("refund|money back", "issue_refund"),
        ("dispute", "dispute_charge"),
        ("charge|bill|invoice|fee", "get_billing_history"),
        ("technician|send someone|come out", "schedule_technician"),
        ("diagnostic|test my line", "run_line_diagnostics"),
        ("outage|down|dropping|slow|not working|noisy", "check_outage_status"),
        ("upgrade|downgrade|plan", "change_plan"),
        ("balance|account|paying", "get_account_summary")]

def arm_keyword(sc):
    t0 = time.perf_counter()
    text = " ".join(x["text"] for x in sc["transcript"] if x["role"] == "customer").lower()
    tool = "transfer_to_human"
    for pat, t in KEYS:
        if re.search(pat, text): tool = t; break
    return Decision(tool, (time.perf_counter()-t0)*1000)

# ------------------------------------------------- LLM plumbing
_oa = None
def _openai():
    global _oa
    if _oa is None:
        import openai; _oa = openai.OpenAI()
    return _oa

def _llm(msgs, mx=400):
    t0 = time.perf_counter()
    r = _openai().chat.completions.create(model=LLM_MODEL, messages=msgs, temperature=0,
        max_completion_tokens=mx, response_format={"type": "json_object"})
    ms = (time.perf_counter()-t0)*1000
    pin, pout = LLM_PRICES.get(LLM_MODEL, (0.40, 1.60))
    return r.choices[0].message.content, ms, (r.usage.prompt_tokens*pin + r.usage.completion_tokens*pout)/1e6

def _json(s):
    try: return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.S); return json.loads(m.group(0)) if m else {}

# ------------------------------------------------- arm B: LLM, whole job
WHOLE_SYS = f"""You route a telecom voice agent to exactly one tool. Read the catalog and
the routing rules, then the conversation, and pick the single next tool.

{SPEC}

Respond with JSON only: {{"tool": "<one tool name>", "reason": "<one sentence>"}}"""

def arm_llm_whole(sc):
    txt, ms, c = _llm([{"role":"system","content":WHOLE_SYS},{"role":"user","content":render(sc)}])
    t = str(_json(txt).get("tool","")).strip()
    return Decision(t if t in TOOLS else "transfer_to_human", ms, {}, c, txt)

# ------------------------------------------------- arm C: LLM, decomposed
DEC_SYS = ("""Answer each question with the probability (0.0-1.0) that it is TRUE, and pick the
caller's MOST RECENT intent. Judge only what the conversation and notes support.
Return JSON only: one key per question plus "latest_intent".

QUESTIONS
""" + "\n".join(f"- {k}: {v}" for k,v in QUESTIONS.items())
  + "\n\nlatest_intent, one of:\n" + "\n".join(f"- {k}: {v}" for k,v in INTENTS.items()))

def arm_llm_decomposed(sc):
    txt, ms, c = _llm([{"role":"system","content":DEC_SYS},{"role":"user","content":render(sc)}])
    d = _json(txt); sem = {}
    for k in QUESTIONS:
        try: sem[k] = float(d.get(k, 0.0))
        except Exception: sem[k] = 0.0
    intent = str(d.get("latest_intent","other")).strip()
    return Decision(route(sc, sem, intent), ms, sem, c, txt)

# ------------------------------------------------- Jev plumbing
_ts = None
def _typesafe():
    global _ts
    if _ts is None:
        from typesafe_sdk import TypeSafeClient; _ts = TypeSafeClient()
    return _ts
def _jcost(u):
    return ((getattr(u,"input_tokens",0)*0.042)+(getattr(u,"output_tokens",0)*0.168))/1e6 if u else 0.0

# ------------------------------------------------- arm D: Jev, whole job
TOOL_CRITERIA = {
 "authenticate_customer":"Verify the caller's identity before anything account specific.",
 "get_account_summary":"Report current plan, balance or account status.",
 "get_billing_history":"Show past invoices and individual charges.",
 "dispute_charge":"Open a formal dispute on a charge already identified.",
 "issue_refund":"Return money for a charge already established as incorrect.",
 "check_outage_status":"Look up known network outages at the caller's address.",
 "run_line_diagnostics":"Remotely test the caller's line or equipment.",
 "schedule_technician":"Book an on-site field visit.",
 "change_plan":"Upgrade, downgrade or modify the subscription.",
 "cancel_service":"Begin cancellation of the account.",
 "report_fraud":"Handle suspected account takeover or unauthorized access.",
 "transfer_to_human":"Hand the call to a person.",
}
def arm_jev_whole(sc):
    from typesafe_sdk import Choice
    t0 = time.perf_counter()
    r = _typesafe().system_one(state="ROUTING SPEC\n"+SPEC+"\n\n"+render(sc),
        questions={"tool": Choice(
            instructions="Apply the routing rules above in order and pick the single next tool.",
            criteria=TOOL_CRITERIA)})
    ms = (time.perf_counter()-t0)*1000
    a = r.answers["tool"]; t = str(a.choice).strip()
    return Decision(t if t in TOOLS else "transfer_to_human", ms,
                    {"confidence": a.confidence}, _jcost(getattr(r,"usage",None)))

# ------------------------------------------------- arm E: Jev, decomposed
def arm_jev_decomposed(sc):
    from typesafe_sdk import Choice, Noul
    q = {k: Noul(instructions=v) for k, v in QUESTIONS.items()}
    q["latest_intent"] = Choice(
        instructions="What is the caller asking for MOST RECENTLY? If they changed topic, use the later one.",
        criteria=INTENTS)
    t0 = time.perf_counter()
    r = _typesafe().system_one(state=render(sc), questions=q)
    ms = (time.perf_counter()-t0)*1000
    sem = {k: r.answers[k].noul for k in QUESTIONS}
    intent = r.answers["latest_intent"].choice
    return Decision(route(sc, sem, intent), ms, sem, _jcost(getattr(r,"usage",None)))

ARMS = {"keyword_rules": arm_keyword, "llm_whole": arm_llm_whole,
        "llm_decomposed": arm_llm_decomposed, "jev_whole": arm_jev_whole,
        "jev_decomposed": arm_jev_decomposed}
