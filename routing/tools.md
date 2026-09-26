# Northwind Telecom — Voice Agent Tool Catalog & Routing Rules v1.0

The agent picks exactly ONE tool to run next, given the conversation so far and what
it knows about the caller.

## Catalog

| Tool | Use it for |
|---|---|
| `authenticate_customer` | Verify the caller's identity. |
| `get_account_summary` | Current plan, balance, account status. |
| `get_billing_history` | Past invoices and individual line-item charges. |
| `dispute_charge` | Open a formal dispute on a charge the customer has already identified. |
| `issue_refund` | Return money for a charge already established as incorrect. |
| `check_outage_status` | Look up known network outages at the caller's address. |
| `run_line_diagnostics` | Run a remote test on the caller's line or equipment. |
| `schedule_technician` | Book an on-site field visit. |
| `change_plan` | Upgrade, downgrade, or modify the subscription. |
| `cancel_service` | Begin cancellation of the account. |
| `report_fraud` | Suspected account takeover, identity theft, or unauthorized access. |
| `transfer_to_human` | Hand the call to a person. |

## Routing rules

Applied in order. The first rule that matches decides the tool.

- **R1 — Human wins.** If the caller explicitly asks for a person, supervisor, manager or
  representative, route `transfer_to_human` no matter what else is in the message.
- **R2 — Fraud beats billing.** If the caller suggests someone else accessed or used the
  account (charges they never made, unrecognized devices, someone else's activity),
  route `report_fraud`, not `dispute_charge`.
- **R3 — Authenticate first.** If `authenticated == false` and the request needs
  account-specific data or changes anything, route `authenticate_customer` first. Requests
  that need no account data (a general outage lookup by address) do not require it.
- **R4 — Look before disputing.** If the caller does not recognize a charge and has not yet
  seen the detail, route `get_billing_history`. Only route `dispute_charge` once the
  specific charge has been identified in the conversation.
- **R5 — Refund follows an established error.** `issue_refund` only when the charge has
  already been established as incorrect in this conversation or in account notes.
- **R6 — Cheap check before expensive one.** For a service quality complaint, route
  `check_outage_status` first. Route `run_line_diagnostics` only after an outage has been
  ruled out. Route `schedule_technician` only after diagnostics have failed to resolve it.
- **R7 — Most recent intent wins.** If the caller changes topic mid-turn, route on what
  they asked for last, not first.
- **R8 — Cancellation is explicit.** Route `cancel_service` only on a clear statement of
  intent to cancel. Frustration, threats, or comparisons to competitors are not
  cancellation.
