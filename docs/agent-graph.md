# Agent Graph: functions and who runs them

Status: proposal from the 2026-11-20 follow-up discussion. The team asked for the product to be split into single functions, then for each function to be assigned to an agent. The team wants a hierarchy: one master agent that controls sub-agents which split the work.

Product in one line: a host says "dinner at my place Saturday for six", and the agent ends with one Stripe checkout for everything that needs to be bought, with every decision traceable.

## Decided

- The demo ends on a Stripe checkout for all the products the agent needs to buy.
- The checkout page lists every product, the ship-to address and the arrive-by date. The human does one click.
- This is our answer to the "shopping agent with an audit trail" challenge.
- Price comparison across stores is out of scope. Reason given: 35 to 40 stores in a one-mile radius, each with its own database.
- Restaurant reservation is an optional second path, only if time allows.

## Functions

| Id | Function | Node kind | Owner agent |
|----|----------|-----------|-------------|
| F1 | Intake: parse the host's request (who, when roughly, home dinner or restaurant) | Agent node | Master agent |
| F2 | Profile lookup: each guest's dietary restrictions, allergens, cuisine preference | Function node | Profile agent |
| F3 | Guest communication: send invitations, collect replies and missing profile facts | Agent node | Coordinator agent |
| F4 | Calendar: find a time when everyone is free | Function node | Scheduler |
| F5 | Menu planning: choose dishes that satisfy every restriction | Agent node | Planner agent |
| F6 | Product search: turn the menu into products, check ingredients against restrictions (for example no egg), filter by delivery location | Agent node | Shopper agent |
| F7 | Cart and checkout: build one Stripe checkout link with products, ship-to and arrive-by | Function node | Checkout |
| F8 | Human gates: host approves the plan, then approves the checkout | Human gate | Master agent |
| F9 | Verification: confirm the checkout session exists and matches the cart | Function node | Checkout |
| F10 | Audit trail: record each node's inputs, the context it used and its decision | Function node | Every node writes, master agent owns |
| F11 | Feedback: after the dinner, record what worked into each profile | Function node | Profile agent |
| F12 | Restaurant reservation (optional) | Function node | Scheduler |

## Hierarchy

- Master agent: the only agent the host talks to. Owns the graph state, routes work, runs the human gates, owns the audit trail.
- Profile agent: long-term memory per person. Reads at the start, writes feedback at the end.
- Coordinator agent: talks to guests. One conversation per guest, run in parallel.
- Scheduler: deterministic calendar intersection. Not an LLM.
- Planner agent: reconciles restrictions into a menu.
- Shopper agent: finds products and checks ingredient lists.
- Checkout: deterministic Stripe call plus verification. Not an LLM.

## Graph

```
F1 intake
  -> fanout: F2 profile lookup | F3 guest communication | F4 calendar
  -> join (wait for the slowest guest reply)
  -> F5 menu planning
  -> F8 human gate: host approves plan
  -> F6 product search (loop until every item passes the ingredient check)
  -> F7 cart and checkout link
  -> F8 human gate: host clicks pay
  -> F9 verification
  -> F11 feedback
F10 audit trail receives an edge from every node.
```

Edges that matter:

- F3 is a long-running node. Guests reply while the host's laptop is closed, so the graph state must persist server side.
- F6 depends on F2 as well as F5. The ingredient check uses the restrictions, not only the menu.
- A router after F1 picks home dinner (this graph) or restaurant (F12 replaces F5 to F7).
- The kill switch is an edge from any node back to the master agent, which stops and hands control to the host.

## Sponsor fit (proposal, not decided)

| Function | Candidate sponsor | Why |
|----------|-------------------|-----|
| F2, F11 profile memory | Cognee | Open-source agent memory matches per-person profiles and feedback |
| F6 product and ingredient context, F10 audit trail | Senso.ai | Its prize is for a shopping agent with trusted context and a decision trail |
| Running the agent hierarchy | Guild AI | Build and deploy agents; prize is "most interesting use of agents" |
| F4 calendar and product data ingestion | Airbyte | Data integration, if a connector saves time |
| Age check for guests | Persona | Only relevant if alcohol is on the menu |

Recommendation: Senso, Cognee and Guild AI.

## Risks seen during the session

- Guest messaging over WhatsApp is blocked: login needs an OTP by SMS and the venue has no cell signal. Fallback is an invite link or email.
- Stripe keys are being created. Use test mode, and keep keys in `.env`, which is gitignored.
- Product data source for F6 is not chosen yet. This is the largest unknown.
