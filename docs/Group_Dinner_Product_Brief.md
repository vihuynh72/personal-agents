# Group Dinner, Coordinated by Personal Agents

**Hackathon product brief | Working scope | November 20, 2026**

## Product idea

Each person's agent represents their preferences and helps the group agree on a restaurant and time, asking for permission when a compromise is needed.

## Problem and target user

Friends planning dinner have different dietary requirements, budgets, locations, and availability. The organizer has to collect everyone's requirements, compare options, and chase confirmations. People may also feel uncomfortable explaining personal constraints in a group chat.

Our first users are small groups of 3–6 friends planning one meal in one city. The demo uses three participants.

## User promise

**Tell your agent what works for you. Get a dinner plan everyone has explicitly accepted.**

## MVP user flow

1. **Create:** The organizer enters the date, general area, and expected participants, then shares a join link.
2. **Set preferences:** Each participant privately enters dietary requirements, budget, availability, travel limit, and optional cuisine preferences. They mark requirements as must-have or flexible.
3. **Coordinate:** Each personal agent evaluates a shared restaurant shortlist against its user's requirements. A coordinator combines the responses and identifies feasible plans or specific conflicts.
4. **Resolve:** When needed, an agent privately asks its user about one concrete adjustment. The user can accept or keep the original requirement. The system then checks the updated plan for everyone.
5. **Confirm:** Each person reviews the same restaurant, time, estimated cost, and relevant notes. Only unanimous approval produces a confirmed group plan.

## Demo story

Alex requires vegan options. Sam has a firm $25 total meal budget, including estimated tax and tip. Jamie is available after 7 p.m. and prefers a journey under 15 minutes, but is willing to discuss distance.

The shortlist contains one restaurant that meets the dietary, budget, and time requirements, but is 25 minutes from Jamie. Jamie's agent asks: “This option meets the group's requirements, but it is 25 minutes away. Would you accept the longer trip?”

Jamie accepts. All three review and confirm the 7:30 p.m. plan. The final card shows the restaurant, address, time, estimated per-person cost, and confirmation status. If Jamie declines and no other option works, the system explains that no match was found; it does not manufacture agreement.

## Scope

| Must build | Out of scope |
| --- | --- |
| Shared session and join link | Full account system and long-term memory |
| Separate participant profiles and private adjustment requests | Calendar, messaging, and payment integrations |
| Small restaurant dataset with menu, cost, and location information | Comprehensive live restaurant coverage |
| Individual agent evaluations and group coordination | Unlimited negotiation rounds |
| One conflict-and-permission loop | Real booking or payment |
| Unanimous confirmation and final plan card | Guaranteed allergy safety |

Use a small curated or clearly labeled synthetic dataset if live search slows development. Label estimated costs and travel times. A confirmed group plan is not a restaurant reservation.

## Agent and interaction rules

- Hard requirements are never relaxed automatically. Flexible preferences change only within explicit user authorization.
- Unknown dietary information remains “needs confirmation”; an agent cannot infer suitability from missing information. The main demo uses vegan requirements rather than allergy clearance.
- Each agent accesses its own user's profile. The coordinator receives only authorized constraints, option evaluations, and approvals. The shared screen does not expose private reasons or raw agent conversations.
- Show meaningful status: who has submitted, what is being checked, and whose decision is needed.
- If a participant has not responded, remain pending. If no feasible plan exists, allow users to revise requirements or end the session.
- Confirmations apply to one plan version. Changing the restaurant, time, or estimated cost invalidates previous confirmations.

## Definition of done

- Three participants can join the same session and submit separate preferences.
- Agents use those preferences to evaluate options, rather than replaying scripted dialogue.
- The demo identifies a real conflict in the supplied data, asks the relevant user, and responds correctly to both acceptance and refusal.
- No proposed final plan violates a declared hard requirement; missing information is visible.
- The plan becomes confirmed only after all three approve the same version.
- The complete demo can be shown in approximately three minutes, with simulated steps identified.

## Team ownership

| Role | Owns |
| --- | --- |
| PM / Product Designer | Scope, user flow, interaction rules, key screens and copy, acceptance testing, demo narrative |
| Engineer A | Frontend, join flow, participant views, shared progress and confirmation UI |
| Engineer B | Personal-agent evaluation, coordinator logic, conflict resolution |
| Engineer C | Restaurant data, session storage, integration, deployment |

## Demo pitch

“Planning dinner should not turn one friend into everyone's coordinator. Each person's agent represents their needs, asks before making compromises, and helps the group reach a plan everyone accepts.”

Our focus is a dedicated workflow for multiple people's preferences, permissions, and confirmations. We are not claiming that Muse cannot perform these tasks.
