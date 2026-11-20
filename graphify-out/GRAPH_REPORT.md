# Graph Report - personal-agents  (2026-11-20)

## Corpus Check
- Corpus is ~3,273 words - fits in a single context window. You may not need a graph.

## Summary
- 121 nodes · 240 edges · 12 communities (9 shown, 3 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 42 edges (avg confidence: 0.85)
- Token cost: 136,671 input · 0 output

## Community Hubs (Navigation)
- Profiles, Calendar and Fanout
- Brainstorm, Stack and Sponsors
- Stripe Checkout and Decisions
- Master Agent, Gates and Audit Trail
- Agent Hierarchy and Gatherings Concept
- Menu, Product Search and Routing
- ADK Graph Workflow Basics
- Guest Messaging and Persistence
- Voice and Accessibility
- No Medical Advice
- Clothing Agent (rejected)
- Out-of-Stock Substitution (rejected)

## God Nodes (most connected - your core abstractions)
1. `Agentic Gatherings (group dinner and party agent)` - 17 edges
2. `F10 Audit Trail (inputs, context, decision per node)` - 16 edges
3. `Graph Workflow (nodes and edges)` - 13 edges
4. `Master Agent (only agent the host talks to)` - 12 edges
5. `F6 Product Search (menu to products, ingredient check, delivery filter)` - 11 edges
6. `Function Node` - 10 edges
7. `Hackathon Brief: Personal Agents Hackathon (tokens&)` - 10 edges
8. `Sponsor Selection Guidance (pick two or three)` - 9 edges
9. `Personal Agent Profile (calendar, dietary restrictions, allergens, cuisine, age)` - 9 edges
10. `Open Questions (mode, demo action, data sharing, sponsors, owners, Senso eligibility)` - 9 edges

## Surprising Connections (you probably didn't know these)
- `Firedrill (simulation platform for testing agents)` --conceptually_related_to--> `Verification Loop`  [AMBIGUOUS]
  docs/hackathon-brief.md → docs/agentic-graph-guide.md
- `Risk: WhatsApp Guest Messaging Blocked` --conceptually_related_to--> `Open Questions (mode, demo action, data sharing, sponsors, owners, Senso eligibility)`  [INFERRED]
  docs/agent-graph.md → docs/brainstorm.md
- `Graphify Knowledge Graph (shared memory)` --references--> `personal-agents (README)`  [EXTRACTED]
  docs/brainstorm.md → README.md
- `Master Agent (only agent the host talks to)` --implements--> `Pure Multi-Agent System (sub-agent tree)`  [INFERRED]
  docs/agent-graph.md → docs/agentic-graph-guide.md
- `Persona (detect agents, verify people; age and identity verification)` --implements--> `Function Node`  [INFERRED]
  docs/hackathon-brief.md → docs/agentic-graph-guide.md

## Hyperedges (group relationships)
- **Agentic Gatherings Coordination Flow (profile, time check, preference check, approval, booking verification)** — docs_brainstorm_personal_agent_profile, docs_brainstorm_time_check, docs_brainstorm_preference_check, docs_agentic_graph_guide_human_gate, docs_agentic_graph_guide_verification_loop, docs_agentic_graph_guide_audit_trail [INFERRED 0.85]
- **Graph Workflow Edge Patterns** — docs_agentic_graph_guide_node_to_node, docs_agentic_graph_guide_fanout_and_fanin, docs_agentic_graph_guide_router, docs_agentic_graph_guide_loop [EXTRACTED 1.00]
- **Design Principles the Team Agreed On** — docs_brainstorm_action_not_chat, docs_brainstorm_human_yes_or_no, docs_brainstorm_butler_agent, docs_brainstorm_learn_from_feedback, docs_brainstorm_show_the_work, docs_brainstorm_kill_switch, docs_brainstorm_lid_closed_cloud_agent, docs_brainstorm_be_specific, docs_brainstorm_no_medical_advice, docs_brainstorm_domain_data [EXTRACTED 1.00]
- **Agent Hierarchy (master agent and six sub-agents)** — docs_agent_graph_master_agent, docs_agent_graph_profile_agent, docs_agent_graph_coordinator_agent, docs_agent_graph_scheduler, docs_agent_graph_planner_agent, docs_agent_graph_shopper_agent, docs_agent_graph_checkout [EXTRACTED 1.00]
- **Home Dinner Flow (F1 to F11, F10 receives from every node)** — docs_agent_graph_f1, docs_agent_graph_f2, docs_agent_graph_f3, docs_agent_graph_f4, docs_agent_graph_f5, docs_agent_graph_f8, docs_agent_graph_f6, docs_agent_graph_f7, docs_agent_graph_f9, docs_agent_graph_f11, docs_agent_graph_f10 [EXTRACTED 1.00]

## Communities (12 total, 3 thin omitted)

### Community 0 - "Profiles, Calendar and Fanout"
Cohesion: 0.18
Nodes (13): F11 Feedback (record what worked into profiles), F2 Profile Lookup (restrictions, allergens, cuisine), F4 Calendar (time everyone is free), Join (wait for slowest guest reply), Profile Agent (long-term memory per person), Scheduler (deterministic calendar intersection), Idea: Dietary Label Reader, Google Calendar (+5 more)

### Community 1 - "Brainstorm, Stack and Sponsors"
Cohesion: 0.12
Nodes (14): Brainstorm: 2026-11-20 Team Session, Claude, Gemini, Vercel (front end only), Amplitude + Statsig (agent analytics, flags, experimentation), Arcee AI (open-weight foundation models), Judging (no published criteria), Hackathon Brief: Personal Agents Hackathon (tokens&) (+6 more)

### Community 2 - "Stripe Checkout and Decisions"
Cohesion: 0.20
Nodes (13): Agent Graph: functions and who runs them, F7 Cart and Checkout (one Stripe checkout link), Decision: Price Comparison Out of Scope, Risk: Stripe Keys Pending (use test mode, keys in .env), Decision: Demo Ends on One Stripe Checkout, Idea: Butler Shopping Agent, Host Mode, Idea: Lifestyle Food Agent (+5 more)

### Community 3 - "Master Agent, Gates and Audit Trail"
Cohesion: 0.20
Nodes (8): Checkout (deterministic Stripe call plus verification), F10 Audit Trail (inputs, context, decision per node), F8 Human Gates (approve plan, approve checkout), F9 Verification (checkout session matches cart), Kill Switch Edge (any node back to master agent), Master Agent (only agent the host talks to), Planner Agent (reconciles restrictions into a menu), Shopper Agent (finds products, checks ingredient lists)

### Community 4 - "Agent Hierarchy and Gatherings Concept"
Cohesion: 0.22
Nodes (10): Agent Hierarchy (master agent over sub-agents), Sponsor Fit (proposal: Senso, Cognee, Guild AI), Add-Friend Mode (limited data access), Agentic Gatherings (group dinner and party agent), Luma (traditional events app; positioning reference), Open Questions (mode, demo action, data sharing, sponsors, owners, Senso eligibility), Airbyte (open-source data integration), Firedrill (simulation platform for testing agents) (+2 more)

### Community 5 - "Menu, Product Search and Routing"
Cohesion: 0.23
Nodes (9): F1 Intake (parse host request), F12 Restaurant Reservation (optional), F5 Menu Planning (dishes satisfying every restriction), F6 Product Search (menu to products, ingredient check, delivery filter), Risk: Product Data Source for F6 Not Chosen, Router after F1 (home dinner vs restaurant), Dinner Mode, Idea: Party and Event Agent (+1 more)

### Community 6 - "ADK Graph Workflow Basics"
Cohesion: 0.21
Nodes (4): Google Agent Development Kit (ADK), Agentic AI Builder Lab with Google Cloud (AI Camp SF, 2026-11-19), Agentic Graph and Workflow Guide, Annie Wong (Developer Relations Engineer, Google Cloud)

### Community 7 - "Guest Messaging and Persistence"
Cohesion: 0.27
Nodes (5): Coordinator Agent (one parallel conversation per guest), F3 Guest Communication (invitations, replies, missing facts), Risk: WhatsApp Guest Messaging Blocked, Railway (backend and long-running agents), SingleStore (real-time data for agents)

### Community 8 - "Voice and Accessibility"
Cohesion: 0.67
Nodes (3): Idea: Accessibility Agent, Deepgram (speech), Idea: Voice-Only Personal Agent

## Ambiguous Edges - Review These
- `Verification Loop` → `Firedrill (simulation platform for testing agents)`  [AMBIGUOUS]
  docs/hackathon-brief.md · relation: conceptually_related_to

## Knowledge Gaps
- **24 isolated node(s):** `personal-agents (README)`, `Annie Wong (Developer Relations Engineer, Google Cloud)`, `Google Agent Development Kit (ADK)`, `tokens& (host, San Francisco, 2026-11-20)`, `Schedule (4:30 PM PT submission deadline)` (+19 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 28 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Agentic Gatherings (group dinner and party agent)` connect `Agent Hierarchy and Gatherings Concept` to `Profiles, Calendar and Fanout`, `Brainstorm, Stack and Sponsors`, `Stripe Checkout and Decisions`, `Master Agent, Gates and Audit Trail`, `Menu, Product Search and Routing`, `ADK Graph Workflow Basics`, `Guest Messaging and Persistence`?**
  _High betweenness centrality (0.220) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `F10 Audit Trail (inputs, context, decision per node)` (e.g. with `Audit Trail (recorded path through the graph)` and `Principle: Show the Work`) actually correct?**
  _`F10 Audit Trail (inputs, context, decision per node)` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `personal-agents (README)`, `Annie Wong (Developer Relations Engineer, Google Cloud)`, `Google Agent Development Kit (ADK)` to the rest of the system?**
  _24 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Brainstorm, Stack and Sponsors` be split into smaller, more focused modules?**
  _Cohesion score 0.125 - nodes in this community are weakly interconnected._
- **Why does `Graph Workflow (nodes and edges)` connect `ADK Graph Workflow Basics` to `Profiles, Calendar and Fanout`, `Master Agent, Gates and Audit Trail`, `Menu, Product Search and Routing`, `Guest Messaging and Persistence`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Why does `Hackathon Brief: Personal Agents Hackathon (tokens&)` connect `Brainstorm, Stack and Sponsors` to `Stripe Checkout and Decisions`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Verification Loop` and `Firedrill (simulation platform for testing agents)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._