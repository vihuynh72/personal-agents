# Saturday Dinner at Home, Coordinated by Personal Agents

**Hackathon product brief | Revised working scope | November 20, 2026**

## Scenario and product idea

“I’m hosting dinner at my place this Saturday for six people. Help me figure out what everyone can eat, plan the menu, and get the groceries ready to buy.”

For the MVP, six people means one host and five guests. The host sets the time and location; the product coordinates food planning and grocery preparation.

Each guest’s personal agent represents their dietary requirements and preferences. The host’s agent combines those inputs with the host’s budget, cooking time, equipment, and pantry to propose a workable menu and shopping list.

## Problem and user promise

A host has to chase dietary information across messages, choose dishes that work together, estimate portions, check existing ingredients, and figure out what to buy. A late requirement or ingredient substitution can force the host to redo that work.

**Plan a dinner that accommodates your guests, with one consolidated grocery list ready for the host to review.**

The host is the primary user and purchase decision-maker. Guests confirm their own requirements and answer only questions that affect them.

## MVP flow

1. **Create the dinner.** The host enters Saturday’s dinner time, six diners, total grocery budget, available cooking time, and equipment, then shares an invite link.
2. **Collect requirements.** Each guest privately submits dietary requirements, dislikes, and flexible preferences. The host adds their own requirements. Guests choose which food-related details may be shared with the host for preparation; private explanations stay private.
3. **Coordinate the menu.** Guest agents evaluate candidate dishes for their users. The host’s agent proposes a shared menu that respects hard requirements and cooking constraints. Show what each person can eat and identify missing information.
4. **Resolve a conflict.** Ask the relevant person about a specific change, such as a different dish or serving a spicy topping separately. Hard dietary requirements are never negotiated away.
5. **Prepare groceries.** Scale recipe quantities to the people eating each dish, merge duplicate ingredients, subtract pantry quantities confirmed by the host, and calculate purchasable pack quantities and estimated costs.
6. **Review and approve.** The host reviews the menu, outstanding checks, shopping list, and total estimate, then approves the list or a draft cart. No purchase occurs automatically.

## Demo story

The host plans Saturday dinner at 7 p.m. for six people, with an illustrative $100 grocery budget and 90 minutes of preparation time.

One guest is vegan. Another cannot tolerate spicy food. A third dislikes mushrooms. The remaining guests have no declared dietary restrictions.

The host initially suggests creamy mushroom pasta. Guest agents identify the dairy and mushroom conflicts. The host’s agent proposes tomato-and-chickpea pasta, a salad with a specified vegan dressing, and fruit. Chili is served separately.

The host approves the revised menu and confirms the quantities of pasta, oil, and salt already at home. The agent produces one shopping list for six, with remaining quantities, package sizes, and an estimated total.

**Demo change:** The host adds, “One more guest is vegan.” The system updates that guest’s profile, rechecks the menu, and keeps the grocery list unchanged if the shared menu already fits. It explains why no extra purchase is needed.

Use a curated recipe and product dataset. Do not claim live prices, stock, or dietary verification when using fixtures.

## Scope

| Must build | Stretch / out of scope |
| --- | --- |
| One host, five guests, invitation link | Full registration, calendar syncing |
| Separate requirements and response status | Long-term personal memory |
| Menu proposal and per-person suitability view | Restaurant search or reservations |
| One conflict-and-permission loop | Unlimited negotiation |
| Recipe quantities, pantry deduction, consolidated list | Automatic pantry recognition |
| Estimated cost and host approval | Live checkout, payments, bill splitting |
| Draft cart or shopping-list output | Delivery tracking, autonomous purchasing |

The core endpoint is an approved menu and grocery list. A draft cart is optional if time and integrations allow. Neither means an order has been placed.

## Decision and privacy rules

- Distinguish hard dietary requirements from flexible taste preferences; never relax a hard requirement automatically.
- A missing guest response means pending, not “no restrictions.”
- Missing ingredient information remains “needs confirmation.” Do not label a meal allergy-safe. Allergy-related preparation questions must be explicitly reviewed by the host and affected guest; the main demo uses vegan and taste requirements.
- Share the food requirements needed for preparation only with permission. Do not expose private explanations or raw agent conversations.
- Guests confirm their own requirements and any requested adjustments. The host makes the final menu and spending decision; every guest need not approve every grocery item.
- Changes to the menu or products trigger another requirements check. Changes affecting cost or quantities require renewed host approval.
- If constraints cannot be met, explain the conflict and ask the host to change a dish, budget, or preparation plan.
- Count pantry quantities only after host confirmation. Keep recipe quantities separate from quantities purchased in packs. Include applicable estimated taxes and delivery fees in the total, or clearly mark them unknown.

## Key screens

1. Host setup and invitation.
2. Private guest requirements.
3. Host dashboard: responses, proposed menu, and suitability by person.
4. Targeted clarification or adjustment request.
5. Grocery review: need / already have / buy, pack quantities, cost estimate, and approval.

## Definition of done

- One host and five guests can contribute to the same dinner.
- Agents evaluate the submitted requirements rather than replaying scripted dialogue.
- A conflicting dish is identified and revised without silently changing a guest’s hard requirements.
- Every diner has a substantive meal option, not just a side dish.
- The shopping list correctly scales portions, merges ingredients, subtracts confirmed pantry quantities, and shows purchase quantities.
- The host can approve the final plan; missing information and simulated integrations are visible.
- The full flow can be demonstrated in approximately three minutes.

## Team ownership

| Role | Owns |
| --- | --- |
| PM / Product Designer | Scenario, scope, flow, decision rules, key screens and copy, acceptance checks, demo story |
| Engineer A | Host and guest interfaces, invitations, status, grocery review |
| Engineer B | Personal agents, menu coordination, conflict handling, requirement checks |
| Engineer C | Recipe/product data, quantity calculations, session storage, optional cart integration, deployment |

## Demo pitch

“Hosting six friends for dinner should not mean chasing five people for dietary requirements and rebuilding your shopping list every time something changes. Our personal agents coordinate guests’ needs, help the host plan the menu, and turn it into a grocery list ready to review and buy.”

Our focus is coordinating multiple people’s requirements into one host-owned cooking and shopping plan. We do not claim that Muse cannot perform these tasks.
