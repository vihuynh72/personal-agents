# Agent Graph: functions and who runs them

Status: proposal from the 2026-11-20 follow-up discussion. The team asked for the product to be split into single functions, then for each function to be assigned to an agent. The team wants a hierarchy: one master agent that controls sub-agents which split the work.

Product in one line: a host says "dinner at my place Saturday for six", and the agent ends with one Stripe checkout for everything that needs to be bought, with every decision traceable.

## Decided

- The demo ends on a Stripe checkout for all the products the agent needs to buy.
- The checkout page lists every product, the ship-to address and the arrive-by date. The human does one click.
- This is our answer to the "shopping agent with an audit trail" challenge.
- Broad price comparison across every local store is out of scope. Reason given: 35 to 40 stores in a one-mile radius, each with its own database.
- Bounded price match is in: every product is looked up on at least two online sources (Walmart was named), pulled from the web, and the agent compares price and pack size.
- Product and ingredient data is loaded into Senso as the trusted context.
- The final link is editable: the host can change quantity, switch pack size (for example 32-pack to six-pack) or pick a different version of a product before paying.
- Payment flow: Stripe charges the host's card. After payment succeeds, fulfilment sub-agents place the orders with the retailers through connectors, running on a cloud machine with the team's own established merchant credentials. The host's shipping address and contact details are auto-filled so they receive the receipts.
- The team does not hold the host's Gmail or retailer logins.
- Guest and host texting goes through Photon. Telegram is the fallback.
- Deployment target is Railway.
- Restaurant reservation is an optional second path, only if time allows.

## Functions

| Id | Function | Node kind | Owner agent |
|----|----------|-----------|-------------|
| F1 | Intake: parse the host's request (who, when roughly, home dinner or restaurant) | Agent node | Master agent |
| F2 | Profile lookup: each guest's dietary restrictions, allergens, cuisine preference | Function node | Profile agent |
| F3 | Guest communication: send invitations, collect replies and missing profile facts | Agent node | Coordinator agent |
| F4 | Calendar: find a time when everyone is free | Function node | Scheduler |
| F5 | Menu planning: choose dishes that satisfy every restriction | Agent node | Planner agent |
| F6 | Product search: turn the menu into products, pull each from at least two web sources, check ingredients against restrictions (for example no egg), compare price and pack size, filter by delivery location | Agent node | Shopper agent |
| F7 | Cart and checkout: build one editable cart link (quantity, pack size, product swap) that ends in a Stripe checkout with products, ship-to and arrive-by | Function node | Checkout |
| F13 | Fulfilment: after Stripe confirms payment, place the orders with each retailer through connectors using the team's merchant credentials | Agent node | Fulfilment agent |
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
- Fulfilment agent: one sub-agent per retailer, triggered by the Stripe payment event, places the order from the cloud machine.

## Graph

```
F1 intake
  -> fanout: F2 profile lookup | F3 guest communication | F4 calendar
  -> join (wait for the slowest guest reply)
  -> F5 menu planning
  -> F8 human gate: host approves plan
  -> F6 product search (loop until every item passes the ingredient check)
  -> F7 cart and checkout link
  -> F8 human gate: host edits the cart and clicks pay
  -> F13 fulfilment (fanout: one sub-agent per retailer)
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

Team position after the follow-up: Airbyte and Guild AI for sure. Senso, Persona, SingleStore, Cognee and Amplitude were all named as wanted. The team believes three sponsor tools is the minimum; the hackathon page does not state this.

Decided by the team: six sponsors. Build them in this order, so the demo still works if the later ones do not land.

1. Senso.ai: trusted product and ingredient context for F6, and the decision trail for F10. This is the challenge's own sponsor.
2. Guild AI: runs the master agent and sub-agents.
3. Cognee: holds the memory, the per-person profiles for F2 and F11.
4. Airbyte: pulls product data from the two web sources into one place.
5. Firedrill: tests the agents, by simulating guests with conflicting restrictions and checking the cart still passes.
6. Persona: verifies the host is a real person at the checkout gate (F8), before agents spend on their behalf.

An earlier recommendation was four sponsors, leaving out Persona. The team chose six.

Left out: SingleStore (no real-time data need yet), Amplitude (analytics does not appear in the demo).

## Owners

| Piece | Owner |
|-------|-------|
| Agent structure, backend, agentic workflow, initiating the sub-agents | Vi |
| Front end: app design and pages | The teammate who is strongest at user interface |
| Sponsor integrations (Senso, Airbyte, Firedrill, Persona) | Unassigned |
| Demo video and submission | Unassigned |

## Risks seen during the session

- WhatsApp login was blocked by a missing SMS code. Resolved by choosing Photon for texting.
- Stripe keys are being created. Use test mode, and keep keys in `.env`, which is gitignored.
- Card data: the host's card number must never be stored on the cloud machine. Stripe holds the card; the system keeps only the Stripe customer and payment ids, plus shipping address and contact details.
- F13 real purchases: retailer sites block automated checkout and the team's merchant card would be charged for real orders. For the demo, F13 runs against a simulated retailer connector and is labelled as simulated in the audit trail.
- Web pulls from retailer sites can be blocked or slow. Cache the pulled products so the demo does not depend on a live scrape.
