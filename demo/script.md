# Demo script and voiceover

Owner: Jing. Draft to edit. Target length: two minutes. Voiceover is written to be read by ElevenLabs, so sentences are short and there are no symbols to pronounce.

Rule for the recording: only show what actually runs. Fulfilment is simulated, and the voiceover says so.

## Flow

| # | Screen | Voiceover |
|---|--------|-----------|
| 1 | Title | Planning a dinner for six friends takes one group chat, forty messages, and somebody still gets served something they cannot eat. |
| 2 | Host types one request | Our agent takes one sentence from the host. Dinner at my place, Saturday, six people. |
| 3 | Graph view: three branches light up in parallel | A master agent splits the work. One sub-agent loads each guest's dietary profile from memory. One texts the guests. One checks every calendar. They run in parallel, and the workflow waits for the slowest reply. |
| 4 | Plan card with time and menu, approve button | The planner agent finds a time that works and a menu that every guest can eat. The host approves with one tap. |
| 5 | Product search with ingredient lists | The shopper agent turns the menu into products. It pulls each one from two stores, reads the full ingredient list, and rejects anything that breaks a guest's restriction. |
| 6 | Editable cart, each item with its reason | The host gets one cart. Every item shows why it was chosen and which guests it was checked against. The host can change a quantity or swap a pack size. |
| 7 | Stripe checkout with ship-to and arrive-by | Then one checkout. The host pays once. They never log in to a store. |
| 8 | Audit trail view | Every step is recorded. What the agent knew, what it decided, and why. This is the audit trail. |
| 9 | Fulfilment status, labelled simulated | After payment, sub-agents place the orders from our own merchant account. In this demo, that last step runs against a simulated store. |
| 10 | Closing slide | One sentence in. One click to pay. Every decision traceable. |

## Technical slides (for the deck)

Judges want the technical problem and how it is solved. Four slides, between screens 2 and 3 or after the demo.

1. The problem, technically: constraint satisfaction across several people's private data (calendars, restrictions), ending in a real purchase that the buyer must be able to trust.
2. The graph: master agent, fanout to profile, messaging and calendar, join, planner, human gate, shopper loop, checkout, verification. Use the diagram from `docs/agent-graph.md`.
3. Agent nodes versus function nodes: models only where judgment is needed (planning, ingredient reasoning); plain code for calendar, checkout and verification. This is why it is reliable.
4. Trust: human gates before plan and payment, the per-item reason, the audit trail, and the card never leaving Stripe. Then the sponsor tools and what each one does.

## To fill in once built

- Real guest names and restrictions for the demo scenario (suggested: one vegetarian, one egg allergy, one halal, one no restriction).
- Which sponsor tools actually made it in. Only name the ones that run.
