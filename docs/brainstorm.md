# Brainstorm: 2026-11-20 team session

Distilled from the recorded team discussion. Statements are what the team said, not verified facts. Status of each idea is marked.

## Converged direction: agentic gatherings (group dinner and party agent)

Status: adopted. The demo is host mode ending on a Stripe checkout. The function and agent breakdown is in `docs/agent-graph.md`.

Scenario: "We want to have dinner tonight, six people, and everyone's preference is different." Today one organizer has to ask every person for availability and food preference. That takes time.

How it works:

1. The organizer tells their personal agent they want to gather a group.
2. Each invited person has a personal agent holding their profile: calendar, dietary restrictions, allergens, cuisine preference, age.
3. The organizer's agent asks the other agents for availability. This is the time check.
4. The agent finds a restaurant or venue that satisfies everyone's food preferences. This is the preference check.
5. The agent proposes a plan. The organizer approves it.
6. The agent sends invitations. Each invitee's agent asks its own human to accept.
7. The agent makes the reservation or books the tickets.

Modes:

- Dinner mode: pick a restaurant for a group, or cook together.
- Party mode: plan a whole night end to end (events, tickets, route, pre-game), and re-plan if ticket prices change.
- Host mode: when hosting a party, buy food for everyone using the known dietary restrictions. This is where the shopping task and Stripe checkout reconnect to the hackathon challenge.

Add-friend mode: friends get access to a limited part of your data, so an invitation can check their calendar and restrictions.

Positioning: an agentic version of Luma (heard as "Lumen" in the recording). Luma is a traditional events app; ours is agents coordinating on behalf of people.

Concerns raised:

- Agent-to-agent communication was called "sketchy" by one teammate. Privacy of shared data is the worry.
- Coordination can look like a company agent or a scheduler app instead of a personal agent. The answer given: each person owns their own agent, and one agent coordinates.
- Persona can verify age, for example so nobody under 21 is invited to a bar.

## Design principles the team agreed on

- Output should be an action, not a chat reply. The stated target: input is your profile, output is a Stripe checkout.
- The human only says yes or no. The agent does the rest and asks for approval at checkout or booking.
- Butler agent: the agent texts you on your phone proactively. One teammate has an app for texting (Photon was mentioned).
- Learn from feedback: yes and no answers and post-purchase reviews update the profile, so bad recommendations are not repeated.
- Show the work: users do not trust AI to click buy unless they can verify why a product was chosen. Visualize what the agent does in the backend. This matches the audit trail in the challenge.
- Kill switch: the human can stop the agent and take over at any moment.
- Keep working when the laptop lid is closed: the agent runs in the cloud, with continuous memory. The theme asks for more than a chat box.
- Be specific. A generic do-anything agent is just Muse with a front end. Muse already handles browser, apps and Gmail.
- Never give medical advice. Medication timing and skincare are out of scope.
- Use domain data others do not have. For food the differentiator would be fresh ingredient data from restaurants or food producers.

## Ideas considered

| Idea | Summary | Status |
|------|---------|--------|
| Dietary label reader | Vegetarian, vegan and allergy shoppers must read every side of every product. India uses a green mark for vegetarian; here reading labels is hard. Agent captures ingredients and answers. | Folded into the profile. Criticized: identifying allergens is something agents can already do. |
| Lifestyle food agent | Agent knows your diet, schedule and cuisine preference, proposes a dish or full recipe when you say "I want something good", cross-checks your inventory, buys groceries. | Scoped down to food and dietary restriction; feeds host mode. |
| Butler shopping agent | Agent texts you, builds a cart, sends a link, you modify and click yes, it buys from ten different websites. Needs a credential store for Instacart, Costco, Walmart, Temu. | Kept as host mode and as the checkout pattern. |
| Price comparison | Compare a product across sites. | Rejected as too generic and trend dependent. |
| Clothing and sizing agent | Vision model judges fit and style. | Rejected: sizes, styles and fittings are too hard. |
| Caregiver agent | Shop for a retired parent, medication-aware meals. | Rejected: touches medical advice. |
| Out-of-stock substitution | Your usual eggless pancake mix is out of stock while you are in meetings; agent swaps the brand. | Rejected: DoorDash and restaurants already do this. |
| Party and event agent | "Me and my friends are going out Halloween weekend, what do we do?" Plans the night, books early-bird tickets. | Merged into party mode. |
| Voice-only personal agent | Agent responds only to the owner's voice. Deepgram for speech; team has free credits. | Parked: called a headache to implement. |
| Accessibility agent | Voice control of browser and files for disabled users. | Parked. Local store inventory and transit range were noted as accessibility factors. |

One teammate argued against shopping entirely: buying is too personal and trends change week to week.

## Team and stack

- Four people. Vi owns the AI brain: memory, knowledge graph, inference, connecting agents.
- Other roles are unassigned.
- Shared memory: Graphify knowledge graph in this repo, so nobody's agent re-reads raw context.
- Deployment: Railway for backend and long-running agents (a teammate has a paid plan). Vercel is front end only.
- Models and tools mentioned: Claude, Gemini, Deepgram, Stripe, Google Calendar (preferred over Apple Calendar because it has an MCP server).
- Form factor debate: iOS app versus web app versus phone call. Web app favored; an iOS app is not needed.

## Open questions

Answered in the follow-up discussion:

- Mode and demo action: host mode, ending on one Stripe checkout that lists all products with ship-to and arrive-by. This keeps us on the "shopping agent with an audit trail" challenge.
- Architecture: one master agent over sub-agents, a hierarchy.
- Price comparison stays out: too many store databases.

Still open:

1. How do agents share data without leaking it? What does add-friend mode expose?
2. Final sponsor list: see the recommendation in `docs/agent-graph.md`.
3. Who owns front end, integrations, demo video and submission?
4. Does fulfilment place real retailer orders in the demo, or a simulated one?

Answered later, recorded in `docs/agent-graph.md`: product data is pulled from at least two web sources and loaded into Senso; texting goes through Photon.
