# Agentic Gatherings — Host Mode PRD

**Status:** Hackathon MVP definition  
**Working scenario:** Six people total: one host and five guests. Stripe test mode and simulated retailer fulfilment are proposed defaults, pending team agreement.

## Scenario and product idea

> “I’m hosting dinner at my place this Saturday for six people. Check who can come, find food that fits everyone’s dietary needs, and prepare a basket that arrives before dinner.”

A gathering agent coordinates personal agents on behalf of the host and guests, turning individual requirements into a host-approved food purchase.

- **Host agent / master coordinator:** Understands the gathering request, coordinates participants, proposes the food plan, builds the basket, and requests approval.
- **Guest personal agents:** Represent their users’ authorized availability and food requirements, ask their users to accept invitations, and return relevant responses.
- **Supporting functions:** Retrieve product information, check requirements, calculate quantities, send notifications, and prepare checkout. Engineering decides how these functions map to sub-agents.

The host sets the dinner time, budget, delivery destination, and arrive-by deadline. Each guest controls their own data and RSVP. The output is **one reviewable food basket and one Stripe checkout**, with an activity trail.

## Problem and user promise

Hosting requires repeatedly asking friends about availability and dietary needs, deciding what to serve, estimating quantities, and buying suitable food. Changes to attendance or requirements create more work.

**User promise:**

> “Tell your agent who you’re hosting. It coordinates their needs and prepares the food purchase for your approval.”

The agent handles research and coordination in the background. People respond to specific decisions rather than managing every step. The host can inspect the choices, request changes, or stop the agent.

## MVP flow

1. **Create the gathering.** The host confirms the date, time, six participants, total budget, ship-to, and arrive-by. Use an explicit date and timezone.
2. **Check availability and requirements.** Each personal agent returns event-authorized information. Missing responses remain pending. For a fixed time, report conflicts rather than automatically rescheduling.
3. **Propose the food plan.** The host’s agent combines requirements and suggests food for the group. Flag conflicts and missing ingredient evidence. The host approves or requests a revision.
4. **Invite and confirm attendance.** After host approval, each guest’s agent asks its human to accept or decline. Update food quantities for accepted attendees.
5. **Build the basket.** Retrieve product evidence from at least two web sources ingested into Senso. Select products, calculate purchase quantities and total cost, and check delivery information. Price comparison is not required.
6. **Notify and review.** Photon sends the host a review link. Show the basket, selection reasons, sources, total, destination, arrival status, and activity trail.
7. **Approve and check out.** The host approves the exact basket and proceeds to one Stripe checkout. Display verified payment status separately from retailer fulfilment.

**Example conflict:** A proposed creamy mushroom dish conflicts with one guest’s vegan requirement and another’s dislike of mushrooms. The agent proposes a documented alternative and updates the basket without changing either person’s requirements.

## Scope

| In the MVP | Outside the MVP |
| --- | --- |
| One at-home dinner; one host and five guest profiles | Restaurant reservations and whole-night party planning |
| Fixed-time availability checks and separate RSVPs | Complex scheduling negotiation |
| One master coordinator with separately scoped personal agents | A general-purpose assistant or full social network |
| One shared food plan and one conflict-resolution loop | Extensive recipe, cooking, or pantry optimization |
| Product data from two web sources through Senso | Cross-store price comparison or ten-store ordering |
| Basket quantities, costs, provenance, ship-to and arrival status | Guaranteed live stock or delivery without supporting evidence |
| Photon review notification and one Stripe checkout | Autonomous payment, bill splitting |
| Visible activity trail and stop control | Voice-only UI, iOS app, age verification |
| Cloud job persistence and one user-confirmed taste-preference update | Advanced continuous learning |

**Implementation boundaries:**

- A web app is sufficient. Synthetic profiles and availability fixtures are acceptable when labeled.
- Use one simple food plan; choose ingredients or ready-to-serve food before implementation.
- Stripe test checkout with simulated fulfilment is the proposed default. Real retailer ordering remains a team decision.
- Creating a checkout or completing payment does not itself place retailer orders.
- The MVP must end at checkout, not only at a shopping list.

## Decision and privacy rules

- **Separate permission, availability, and RSVP.** Being a friend or being available does not mean someone has shared their profile or accepted an invitation.
- **Share only what this dinner needs.** Personal agents return authorized availability and food requirements. Do not expose raw calendars, private explanations, or unrelated profile data. Enforce access outside the model prompt.
- **Keep decisions with the correct person.** Guests control requirements and attendance. The host approves the food plan, destination, spending, and checkout.
- **Never relax hard restrictions automatically.** A rejection may trigger another proposal; it does not authorize changing dietary requirements.
- **Preserve uncertainty.** Missing ingredient or allergen information is “needs confirmation,” not a suitability claim. Block affected items until required checks are resolved. Do not provide medical advice or guarantee allergy safety.
- **Tie approval to a basket version.** Changes to products, quantities, total, destination, or delivery terms require renewed host approval and invalidate obsolete unpaid checkout sessions.
- **Respect budget and delivery requirements.** Include taxes and delivery fees in the payable total. Distinguish requested arrival time from verified, estimated, or simulated arrival information.
- **Make stop meaningful.** Stop prevents new queued actions and shows what has already happened. It does not automatically reverse payments or cancel retailer orders.
- **Show actions and evidence.** Display concise reasons, sources, timestamps, and outcomes, not private agent conversations.
- **Keep memory scoped.** Store feedback only with user confirmation. Private profiles stay separate from the shared project knowledge graph. Past purchases never establish allergy safety.

## Key screens

| Screen | What users see | Main action |
| --- | --- | --- |
| Host setup | Participants, date/time, budget, ship-to, arrive-by | Start planning |
| Guest view | Event details, sharing permissions, personal requirements, invitation | Share for this dinner; accept or decline |
| Gathering dashboard | Availability, RSVPs, proposed food plan, conflicts, progress | Approve or revise plan |
| Basket review | Products, quantities, evidence, costs, delivery details | Edit; approve and continue to checkout |
| Checkout and outcome | Stripe checkout, verified payment status, separate fulfilment status | Pay in test mode; retry or return if canceled |

Keep the activity trail and stop control accessible while the agent works. Photon links the host back to the relevant review screen.

## Definition of done

- Six profiles contribute through separately scoped personal agents.
- Availability and invitation acceptance are recorded separately.
- A conflict in the supplied data changes the food or product selection.
- Product evidence from two web sources is retrievable through Senso and inspectable.
- Basket quantities match accepted attendance; totals match checkout.
- The host reviews the exact basket, ship-to, arrive-by status, and total before payment.
- Photon sends an authorized review notification.
- One Stripe test checkout completes with a verified result; simulated fulfilment is labeled.
- Stop prevents new queued actions; closing the frontend does not cancel backend work.
- A confirmed taste-preference update affects a subsequent proposal.
- All critical tests below pass. **Current test status: not run.**

### MVP test scenarios

| ID | Scenario | Expected result |
| --- | --- | --- |
| T01 | Six participants accept; complete the full flow | Approved basket, Photon link, one checkout, verified test-payment result |
| T02 | A guest is unavailable, pending, or declines | Show the correct state; no invented RSVP; resolve attendance and update quantities before final approval |
| T03 | A candidate conflicts with a hard dietary requirement | Reject it with evidence and evaluate an alternative; do not change the requirement |
| T04 | Ingredient evidence is missing or sources conflict | Mark needs confirmation; prevent the affected item from being approved as suitable |
| T05 | Total exceeds budget or delivery misses the deadline | Request a revision; no silent overspend or unsupported arrival promise |
| T06 | Basket changes after approval | Invalidate approval and obsolete unpaid checkout; require another review |
| T07 | Payment fails, is canceled, or checkout is clicked twice | No false success or duplicate purchase; deliberate retry remains possible |
| T08 | One guest attempts to access another’s private profile | Access denied; no private data in shared views or the activity trail |
| T09 | Host stops an active job | No new queued external actions; completed/in-flight actions reported accurately |
| T10 | Host closes and reopens the frontend | Work and saved status persist; no duplicate messages or checkout actions |
| T11 | Senso retrieval or Photon notification fails | Show failure without fabricating data or delivery; retain accessible review state and a clear retry path |
| T12 | User confirms a new taste preference | Update only that user’s profile and apply it to the next proposal |
| T13 | Check quantities, prices, and final checkout | Correct pack counts and arithmetic; identical totals and currency in review and checkout |

For each test, record the build, actual result, pass/fail, and evidence. A written scenario is not proof that the behavior works.
