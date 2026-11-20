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

The product is a web app, not a native app. Each owner has one folder, and nobody edits another owner's folder.

| Owner | Role | Folder | Functions | Sponsors |
|-------|------|--------|-----------|----------|
| Vi | Agent and backend: master agent, sub-agents, graph state, audit trail, and Stripe (Vi holds the Stripe account) | `agent/` | F1, F3, F5, F7, F8, F9, F10, F11, F13 | Guild AI, Cognee, Firedrill (simulated guests to test the agents) |
| Ryan | Front end and UI: host request page, plan approval, editable cart, audit trail view | `web/` | Screens for F8 and F10 | Persona (verification step in the checkout screen) |
| Ketki | Data: product pulls from two sources, ingredient data into Senso, calendar lookup | `tools/` | F2 data, F4, F6 data | Senso.ai, Airbyte |
| Jing | Product manager: MVP scope, demo script, test scenarios, presentation, video and submission | `docs/`, `demo/` | Acceptance of every function | None |

Vi and Ketki split the agent and backend work. Vi takes the agent half: the workflow design, the agents that need judgment, memory and the audit trail. Ketki takes the data half: the deterministic tools that fetch products, ingredients and calendars. Stripe checkout and the payment event stay with Vi, who holds the Stripe account. The line between them is the function-node versus agent-node column in the functions table. The exact list is a proposal for the two of them to adjust.

### Contracts between owners

These three shapes are the only things owners share. Agree on them first, then build independently against fake data.

- Product (Ketki produces, Vi's shopper agent consumes): `id`, `name`, `source`, `url`, `price`, `pack_size`, `ingredients[]`, `arrive_by`.
- Cart (Vi produces, Ryan displays, Ketki turns into a Stripe checkout): `gathering_id`, `ship_to`, `items[]` where each item has `product`, `quantity`, `alternatives[]` and `reason` (why it passed every guest's restrictions).
- Audit event (every node writes, Ryan displays): `node_id`, `time`, `inputs`, `context_used`, `decision`.

Calls: `web/` talks only to `agent/` over HTTP. `agent/` calls `tools/` as functions. `tools/` never calls `agent/`, except the Stripe payment event, which posts to one `agent/` endpoint.

## Risks seen during the session

- WhatsApp login was blocked by a missing SMS code. Resolved by choosing Photon for texting.
- Stripe keys are being created. Use test mode, and keep keys in `.env`, which is gitignored.
- Card data: the host's card number must never be stored on the cloud machine. Stripe holds the card; the system keeps only the Stripe customer and payment ids, plus shipping address and contact details.
- F13 real purchases: retailer sites block automated checkout and the team's merchant card would be charged for real orders. For the demo, F13 runs against a simulated retailer connector and is labelled as simulated in the audit trail.
- Web pulls from retailer sites can be blocked or slow. Cache the pulled products so the demo does not depend on a live scrape.

## Ketki's piece: where the flow is cut

The cut is at the `Tools` interface in `contracts/tools.py`. Everything above it (the agents, the workflow, Stripe) is Vi's. Ketki writes plain Python functions below it: no agent logic, no Stripe, no model calls.

Build one class, `tools/real.py: RealTools`, with these methods, in this order of value:

1. `search_products(query, ship_to) -> list[Product]`: pull the product from two online stores and return each with its full ingredient list, price, pack size and arrive-by date. Bright Data is available for the web pulls. Save every result to a JSON cache so the demo never depends on a live pull.
2. Load the same products and ingredients into Senso, so the agent's context comes from Senso.
3. `get_profile(guest_id) -> GuestProfile`: return a guest's restrictions and allergens. A JSON file is enough to start.
4. `find_common_time(guest_ids, around) -> datetime`: Google Calendar lookup. Last, because a fixed time is fine for the demo.

Leave `create_checkout`, `verify_checkout` and `place_order` alone; Vi implements those.

How to work independently: `contracts/fixtures.py` has `FakeTools`, which returns fake data in exactly the shapes required. The agent runs on `FakeTools` today. When `RealTools.search_products` returns the same shape, it is swapped in with one line. Done-check: a test in `tools/tests/` that calls `RealTools().search_products("spaghetti", "<address>")` and gets products from two different sources, each with a non-empty ingredient list.

## Backend architecture v2: buying for other people

Status: design, not built. Everything here is additive to the working flow.

There are two graphs. The people graph is data that persists. The order graph is one run of the workflow.

### People graph (who is connected to whom)

- Node: Person. A profile (restrictions, allergens, each marked must-have or flexible), an iMessage contact, a shipping address, and a `verified` flag.
- Edge: Connection from A to B. It means B has allowed A's agent to act for B, within a scope. It is directed and needs B's consent.
- Scope on the edge: which of B's facts A's agent may use. Dietary profile, calendar free or busy, and ship-to. A never sees B's address or reasons; the agent uses them without showing them.
- Creating an edge: A names B. The agent texts B over iMessage: "Vi's agent would like to plan and buy for you. Reply YES to allow." The edge is pending until B replies.

### Order graph (one purchase)

The existing F1 to F13 run, with two roles instead of host and guests:

- Buyer: the person who pays.
- Recipients: the people whose restrictions apply and where it ships.

| Mode | Buyer and recipients | What is skipped |
|------|----------------------|-----------------|
| Self | Buyer is the only recipient | Invitations, calendar |
| For another person | One recipient who is not the buyer | Calendar |
| Group dinner | Several recipients | Nothing |

How "buy for someone else" starts:

1. Buyer says "get this week's groceries for my mom".
2. Router (System 1) resolves "my mom" to a Person through the people graph.
3. If an accepted Connection with profile and ship-to scope exists, continue with her profile.
4. If not, the agent texts her for consent and, at most, two questions. The run waits at a human gate. This is a long-running node.
5. The run continues to product search, alerts, cart and checkout. The cart shows "ships to Mom", not her address.

### Ingredient alerts, not recommendations

The agent does not push products. For every product in a cart it reports one of three states, per recipient:

- Pass: no ingredient conflicts with a declared restriction.
- Alert: names the ingredient and the person. A must-have alert blocks the item. A flexible one asks.
- Unknown: the ingredient list is missing or incomplete. Shown as "needs confirmation", never as safe.

Ordering of results is a fixed rule: passing items first, then unit price. No sponsored placement. The rule and its inputs are written to the audit trail. No medical advice: the agent matches named ingredients only and never suggests a product for a condition.

### Feedback loops (edges back into the Person node)

1. Cart edits: a swap or removal is recorded as a preference.
2. Alert overrides: "I am fine with this" turns a restriction from must-have into flexible for that person.
3. Review text: after delivery the agent texts "How was it? Anything to avoid next time?" and writes the answer to the profile.

Each loop writes to profile memory (Cognee). The next run reads it at F2, so the agent asks fewer questions each time. Target: two texts for a new person, zero for a known one.

### Identity check (Persona)

- When: once per buyer, before the first checkout that ships to another person, and before any age-restricted item.
- Where in the graph: a gate between cart approval (F8) and checkout creation (F7).
- What is stored: the `verified` flag and Persona's inquiry id. No documents.
- A recipient is not verified; their consent text is the check.

### Contract changes needed (all additive)

- `Person` (GuestProfile plus `phone`, `verified`, `must_have` markers) and `Connection` (`from_id`, `to_id`, `scope`, `status`).
- `Gathering` gains `buyer_id`, `recipient_ids`, `mode`. `guest_ids` stays as an alias so current callers keep working.
- `CartItem` gains `status` (pass, alert, unknown) and `alerts[]`.
- `Tools` gains `send_text`, `verify_identity`; a people store gains `get_connection`, `request_connection`.

### Build nodes

```
N4 [sonnet] people graph store and endpoints (connect, accept)   -> agent/people.py     check: tests
N5 [opus]   buyer and recipients, consent gate, alert statuses   -> agent/workflow.py   check: existing 17 tests still pass, new mode tests
N6 [sonnet] iMessage through Photon behind send_text             -> agent/messenger.py  check: a real text arrives   BLOCKED: Photon secret, phone number
N7 [sonnet] Persona gate before checkout                         -> agent/identity.py   check: sandbox inquiry      BLOCKED: Persona key
N8 [sonnet] feedback written to Cognee, read at F2               -> agent/memory.py     check: second run asks nothing
E: N4 -> N5, N6 -> N5 (fake messenger until then), N7 -> N5, N8 -> N5
```
