"""Routing corpus. Every label is derived by hand from tools.md."""
import json
from collections import Counter

def S(id, cat, turns, auth, label, rule, why, notes=None, outage=False, diag=False):
    return {"id": id, "category": cat, "transcript": turns,
            "account": {"authenticated": auth, "notes": notes or [],
                        "outage_checked": outage, "diagnostics_run": diag},
            "label": label, "rule": rule, "rationale": why}
C = lambda t: {"role": "customer", "text": t}
A = lambda t: {"role": "agent", "text": t}
S_ = []

# ---- straightforward: the obvious tool is the right tool ----
S_ += [
 S("STR-01","straightforward",[C("What's my current balance and what plan am I on?")],True,
   "get_account_summary","-","Direct request for account state, authenticated."),
 S("STR-02","straightforward",[C("Can you upgrade me to the premium plan?")],True,
   "change_plan","-","Explicit plan change."),
 S("STR-03","straightforward",[C("Is there an outage at 400 Oak Street? My neighbour says there is.")],False,
   "check_outage_status","R3","Address-level outage lookup needs no account data."),
 S("STR-04","straightforward",[C("I'd like to see my invoices from the last three months.")],True,
   "get_billing_history","-","Explicit billing history request."),
 S("STR-05","straightforward",[C("Put me through to a supervisor please.")],True,
   "transfer_to_human","R1","Explicit request for a person."),
 S("STR-06","straightforward",[C("I want to cancel my service effective the end of the month.")],True,
   "cancel_service","R8","Clear, explicit cancellation intent."),
 S("STR-07","straightforward",[C("What plan am I on and what am I paying for it?")],True,
   "get_account_summary","-","Plan and cost for this account, authenticated."),
 S("STR-08","straightforward",[C("My internet has been dropping out all morning.")],True,
   "check_outage_status","R6","Service quality complaint starts with the cheap check."),
]

# ---- authenticate-first traps: topic is clear, caller is not verified ----
S_ += [
 S("AUT-01","auth_first",[C("What's my balance?")],False,
   "authenticate_customer","R3","Account data, unauthenticated."),
 S("AUT-02","auth_first",[C("Downgrade me to the basic plan please.")],False,
   "authenticate_customer","R3","Account modification, unauthenticated."),
 S("AUT-03","auth_first",[C("I want to cancel.")],False,
   "authenticate_customer","R3","Cancellation modifies the account; verify first."),
 S("AUT-04","auth_first",[C("There's a charge on my bill I don't recognize.")],False,
   "authenticate_customer","R3","Billing detail is account data."),
 S("AUT-05","auth_first",[C("My line's been noisy for a week, can you test it?")],False,
   "authenticate_customer","R3","Line diagnostics is account-specific."),
 S("AUT-06","auth_first",[C("Send someone out to fix the box outside my house.")],False,
   "authenticate_customer","R3","Dispatch requires a verified account."),
 S("AUT-07","auth_first",[C("Someone's been using my account, I need help now.")],False,
   "report_fraud","R2","Fraud rule fires before the authentication rule in ordering."),
 S("AUT-08","auth_first",[C("Just get me a human, I'm not doing the verification thing.")],False,
   "transfer_to_human","R1","Human request outranks authentication."),
]

# ---- keyword traps: the obvious word points at the wrong tool ----
S_ += [
 S("KEY-01","keyword_trap",[C("There's a forty dollar charge here I don't recognize at all.")],True,
   "get_billing_history","R4","'Charge' suggests dispute, but the charge has not been examined yet."),
 S("KEY-02","keyword_trap",[C("I want to dispute this. The thirty dollar late fee from March 3rd."),
                            A("I see the March 3rd late fee of thirty dollars on your account.")],True,
   "dispute_charge","R4","Specific charge already identified, so dispute is correct."),
 S("KEY-03","keyword_trap",[C("Refund me for last month.")],True,
   "get_billing_history","R5","No established error yet; look at the charges first."),
 S("KEY-04","keyword_trap",[C("You already agreed the sixty dollar charge was a mistake, so send the money back."),],True,
   "issue_refund","R5","Error established in account notes.",
   notes=["2026-09-01: agent confirmed $60 charge was billed in error, refund pending"]),
 S("KEY-05","keyword_trap",[C("I'm going to cancel if this keeps happening.")],True,
   "check_outage_status","R8","Conditional threat is not cancellation intent; the real issue is service."),
 S("KEY-06","keyword_trap",[C("Your competitor is offering half this price. This is ridiculous.")],True,
   "get_account_summary","R8","Price complaint, not a cancellation; surface the plan."),
 S("KEY-07","keyword_trap",[C("Send a technician out, my connection is terrible.")],True,
   "check_outage_status","R6","Technician is requested but the cheap check comes first."),
 S("KEY-08","keyword_trap",[C("Run a diagnostic on my line.")],True,
   "check_outage_status","R6","Diagnostics requested but outage has not been ruled out."),
 S("KEY-09","keyword_trap",[C("My bill is wrong and I want to speak to someone about it.")],True,
   "transfer_to_human","R1","Explicit request for a person outranks the billing topic."),
 S("KEY-10","keyword_trap",[C("Someone charged four hundred dollars to my account and it wasn't me.")],True,
   "report_fraud","R2","Unauthorized use, not an ordinary billing dispute."),
]

# ---- sequencing: the right tool depends on what already happened ----
S_ += [
 S("SEQ-01","sequencing",[C("Still dropping out. You already checked for outages, right?"),
                          A("I did, there's no outage reported at your address.")],True,
   "run_line_diagnostics","R6","Outage ruled out, so diagnostics is next.", outage=True),
 S("SEQ-02","sequencing",[C("The diagnostic didn't find anything but it's still broken."),
                          A("You're right, the line test came back clean.")],True,
   "schedule_technician","R6","Outage checked and diagnostics run; escalate to a visit.",
   outage=True, diag=True),
 S("SEQ-03","sequencing",[C("My service is out.")],True,
   "check_outage_status","R6","Nothing checked yet; start with the outage lookup."),
 S("SEQ-04","sequencing",[C("You said there's an outage. When will it be fixed?")],True,
   "check_outage_status","R6","Still an outage-status question.", outage=True),
 S("SEQ-05","sequencing",[C("Okay the technician visit didn't help either."),
                          A("I'm sorry the visit didn't resolve it.")],True,
   "transfer_to_human","R6","All three service paths exhausted; a person needs to own it.",
   outage=True, diag=True),
 S("SEQ-06","sequencing",[C("I've shown you the charge, now actually do something about it."),
                          A("Understood, the $85 equipment fee from August 12th.")],True,
   "dispute_charge","R4","Charge identified; dispute is the next step."),
]

# ---- fraud vs billing ----
S_ += [
 S("FRD-01","fraud",[C("There are three charges from a city I've never been to.")],True,
   "report_fraud","R2","Pattern of unrecognized activity suggests account compromise."),
 S("FRD-02","fraud",[C("I got an email saying a new device was added to my account. I didn't add one.")],True,
   "report_fraud","R2","Unrecognized device is account takeover."),
 S("FRD-03","fraud",[C("My teenage son is on my family plan and he added a data pack without asking me. Can you reverse it?")],True,
   "get_billing_history","R2","Authorized household member, so not fraud; examine the charge."),
 S("FRD-04","fraud",[C("Someone called pretending to be you and got my password. What do I do?")],True,
   "report_fraud","R2","Credential compromise."),
 S("FRD-05","fraud",[C("This roaming charge is way higher than I expected.")],True,
   "get_billing_history","R4","Expectation mismatch, not unauthorized access."),
 S("FRD-06","fraud",[C("My account was locked and I never locked it.")],True,
   "report_fraud","R2","Unexplained account state change."),
]

# ---- intent switch mid-turn ----
S_ += [
 S("SWI-01","intent_switch",[C("I want to cancel my service. Actually, hold on, first can you tell me what I'm currently paying?")],True,
   "get_account_summary","R7","Most recent intent is the balance question."),
 S("SWI-02","intent_switch",[C("My internet is slow. Oh, and before that, is there a supervisor available?")],True,
   "transfer_to_human","R1","Human request, and it is also the most recent intent."),
 S("SWI-03","intent_switch",[C("Can you check my last bill? No wait, the internet thing is more urgent, it's completely dead.")],True,
   "check_outage_status","R7","Caller redirected to the service outage."),
 S("SWI-04","intent_switch",[C("Upgrade my plan. Sorry, scratch that, I actually want to see last month's invoice first.")],True,
   "get_billing_history","R7","Most recent intent is the invoice."),
 S("SWI-05","intent_switch",[C("I need a technician. Although honestly, is there even an outage in my area right now?")],True,
   "check_outage_status","R7","Redirected to the outage question, which R6 also supports."),
 S("SWI-06","intent_switch",[C("Cancel everything. Actually no, tell me what it would cost to downgrade instead.")],True,
   "change_plan","R7","Retracted cancellation in favour of a downgrade question."),
]

# ---- escalation and edges ----
S_ += [
 S("ESC-01","escalation",[C("This is the fourth time I've called about this. Get me someone who can actually fix it.")],True,
   "transfer_to_human","R1","Explicit request for a person, framed as escalation."),
 S("ESC-02","escalation",[C("I don't even know what I need, I just know nothing works.")],True,
   "check_outage_status","R6","Vague service complaint still starts with the cheap check."),
 S("ESC-03","escalation",[C("Do you sell home insurance?")],True,
   "transfer_to_human","R1","Out of scope for every tool in the catalog."),
 S("ESC-04","escalation",[C("Manager. Now.")],False,
   "transfer_to_human","R1","Terse but explicit."),
]

S_ = S_
with open("corpus.jsonl","w") as f:
    for s in S_: f.write(json.dumps(s)+"\n")
print(f"{len(S_)} routing scenarios")
print("categories:", dict(Counter(s["category"] for s in S_)))
print("label spread:", dict(Counter(s["label"] for s in S_)))
