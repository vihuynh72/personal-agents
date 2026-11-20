# Graph Report - personal-agents  (2026-11-20)

## Corpus Check
- Corpus is ~3,728 words - fits in a single context window. You may not need a graph.

## Summary
- 139 nodes · 305 edges · 13 communities (9 shown, 4 thin omitted)
- Extraction: 84% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 47 edges (avg confidence: 0.85)
- Token cost: 145,556 input · 0 output

## Community Hubs (Navigation)
- F6 Product Search
- F10 Audit Trail
- Agent Graph: functions and who runs them
- Sponsor Selection Guidance
- Hackathon Brief: Personal Agents Hackath
- F3 Guest Communication
- Agentic Gatherings
- Graph Workflow
- Idea: Voice-Only Personal Agent
- Idea: Caregiver Agent
- Idea: Clothing and Sizing Agent
- Idea: Out-of-Stock Substitution

## God Nodes (most connected - your core abstractions)
1. `F10 Audit Trail (inputs, context, decision per node)` - 18 edges
2. `Agentic Gatherings (group dinner and party agent)` - 17 edges
3. `Agent Graph: functions and who runs them` - 16 edges
4. `Master Agent (only agent the host talks to)` - 13 edges
5. `F6 Product Search (menu to products, ingredient check, delivery filter)` - 13 edges
6. `Graph Workflow (nodes and edges)` - 13 edges
7. `Open Questions (data sharing, final sponsor list, owners, real vs simulated fulfilment)` - 13 edges
8. `F7 Cart and Checkout (one Stripe checkout link)` - 11 edges
9. `Sponsor Selection Guidance (pick two or three)` - 11 edges
10. `F8 Human Gates (approve plan, approve checkout)` - 10 edges

## Surprising Connections (you probably didn't know these)
- `Cognee (open-source memory for agents)` --semantically_similar_to--> `Long-Term Memory (memory service)`  [INFERRED] [semantically similar]
  docs/hackathon-brief.md → docs/agentic-graph-guide.md
- `Firedrill (simulation platform for testing agents)` --conceptually_related_to--> `Verification Loop`  [AMBIGUOUS]
  docs/hackathon-brief.md → docs/agentic-graph-guide.md
- `Graphify Knowledge Graph (shared memory)` --references--> `personal-agents (README)`  [EXTRACTED]
  docs/brainstorm.md → README.md
- `F10 Audit Trail (inputs, context, decision per node)` --implements--> `Principle: Show the Work`  [INFERRED]
  docs/agent-graph.md → docs/brainstorm.md
- `F8 Human Gates (approve plan, approve checkout)` --implements--> `Principle: Human Only Says Yes or No`  [INFERRED]
  docs/agent-graph.md → docs/brainstorm.md

## Hyperedges (group relationships)
- **Agent Hierarchy (master agent and seven sub-agents)** — docs_agent_graph_master_agent, docs_agent_graph_profile_agent, docs_agent_graph_coordinator_agent, docs_agent_graph_scheduler, docs_agent_graph_planner_agent, docs_agent_graph_shopper_agent, docs_agent_graph_checkout, docs_agent_graph_fulfilment_agent [EXTRACTED 1.00]
- **Home Dinner Flow (F1 to F11 including F13, F10 receives from every node)** — docs_agent_graph_f1, docs_agent_graph_f2, docs_agent_graph_f3, docs_agent_graph_f4, docs_agent_graph_f5, docs_agent_graph_f8, docs_agent_graph_f6, docs_agent_graph_f7, docs_agent_graph_f13, docs_agent_graph_f9, docs_agent_graph_f11, docs_agent_graph_f10 [EXTRACTED 1.00]
- **Graph Workflow Edge Patterns** — docs_agentic_graph_guide_node_to_node, docs_agentic_graph_guide_fanout_and_fanin, docs_agentic_graph_guide_router, docs_agentic_graph_guide_loop [EXTRACTED 1.00]
- **Design Principles the Team Agreed On** — docs_brainstorm_action_not_chat, docs_brainstorm_human_yes_or_no, docs_brainstorm_butler_agent, docs_brainstorm_learn_from_feedback, docs_brainstorm_show_the_work, docs_brainstorm_kill_switch, docs_brainstorm_lid_closed_cloud_agent, docs_brainstorm_be_specific, docs_brainstorm_no_medical_advice, docs_brainstorm_domain_data [EXTRACTED 1.00]
- **Agentic Gatherings Coordination Flow (profile, time check, preference check, approval, booking verification)** — docs_brainstorm_personal_agent_profile, docs_brainstorm_time_check, docs_brainstorm_preference_check, docs_agentic_graph_guide_human_gate, docs_agentic_graph_guide_verification_loop, docs_agentic_graph_guide_audit_trail [INFERRED 0.85]

## Communities (13 total, 4 thin omitted)

### Community 0 - "F6 Product Search"
Cohesion: 0.14
Nodes (16): Agent Hierarchy (master agent over sub-agents), F12 Restaurant Reservation (optional), F5 Menu Planning (dishes satisfying every restriction), F6 Product Search (menu to products, ingredient check, delivery filter), F8 Human Gates (approve plan, approve checkout), Fulfilment Agent (one sub-agent per retailer, triggered by Stripe payment event), Kill Switch Edge (any node back to master agent), Master Agent (only agent the host talks to) (+8 more)

### Community 1 - "F10 Audit Trail"
Cohesion: 0.17
Nodes (12): Checkout (deterministic Stripe call plus verification), F1 Intake (parse host request), F10 Audit Trail (inputs, context, decision per node), F11 Feedback (record what worked into profiles), F2 Profile Lookup (restrictions, allergens, cuisine), F4 Calendar (time everyone is free), F9 Verification (checkout session matches cart), Join (wait for slowest guest reply) (+4 more)

### Community 2 - "Agent Graph: functions and who runs them"
Cohesion: 0.20
Nodes (19): Agent Graph: functions and who runs them, Decision: Bounded Two-Source Price Match, Decision: Editable Cart Link (quantity, pack size, product swap before paying), F7 Cart and Checkout (one Stripe checkout link), Decision: Team Holds No Host Gmail or Retailer Logins, Decision: Stripe Charges Card, Then Fulfilment Sub-Agents Place Orders, Decision: Price Comparison Out of Scope, Risk: Host Card Data Must Never Be Stored on the Cloud Machine (+11 more)

### Community 3 - "Sponsor Selection Guidance"
Cohesion: 0.25
Nodes (14): Sponsor Fit (proposal: Senso, Cognee, Guild AI), Sponsor Recommendation (Senso, Airbyte, Guild AI, Cognee in priority order), Sponsors Left Out Unless Time Remains (Persona, SingleStore, Amplitude), Graphify Knowledge Graph (shared memory), Open Question: Final Sponsor List, Vi (owns the AI brain: memory, knowledge graph, inference, connecting agents), Airbyte (open-source data integration), Cognee (open-source memory for agents) (+6 more)

### Community 4 - "Hackathon Brief: Personal Agents Hackath"
Cohesion: 0.13
Nodes (13): Brainstorm: 2026-11-20 Team Session, Claude, Gemini, Vercel (front end only), Amplitude + Statsig (agent analytics, flags, experimentation), Arcee AI (open-weight foundation models), Judging (no published criteria), Hackathon Brief: Personal Agents Hackathon (tokens&) (+5 more)

### Community 5 - "F3 Guest Communication"
Cohesion: 0.21
Nodes (7): Coordinator Agent (one parallel conversation per guest), F3 Guest Communication (invitations, replies, missing facts), Decision: Guest and Host Texting via Photon (Telegram fallback), Decision: Deployment Target Is Railway, Risk: WhatsApp Guest Messaging Blocked, Photon (texting app), Railway (backend and long-running agents)

### Community 6 - "Agentic Gatherings"
Cohesion: 0.26
Nodes (9): F13 Fulfilment (place retailer orders after Stripe confirms payment), Risk: F13 Real Purchases (retailers block automation, merchant card charged), Add-Friend Mode (limited data access), Agentic Gatherings (group dinner and party agent), Luma (traditional events app; positioning reference), Open Question: How Agents Share Data Without Leaking It (what add-friend exposes), Open Question: Real Retailer Orders or Simulated in the Demo, Open Question: Who Owns Front End, Integrations, Demo Video, Submission (+1 more)

### Community 7 - "Graph Workflow"
Cohesion: 0.21
Nodes (4): Google Agent Development Kit (ADK), Agentic AI Builder Lab with Google Cloud (AI Camp SF, 2026-11-19), Agentic Graph and Workflow Guide, Annie Wong (Developer Relations Engineer, Google Cloud)

### Community 8 - "Idea: Voice-Only Personal Agent"
Cohesion: 0.67
Nodes (3): Idea: Accessibility Agent, Deepgram (speech), Idea: Voice-Only Personal Agent

## Ambiguous Edges - Review These
- `Verification Loop` → `Firedrill (simulation platform for testing agents)`  [AMBIGUOUS]
  docs/hackathon-brief.md · relation: conceptually_related_to

## Knowledge Gaps
- **23 isolated node(s):** `personal-agents (README)`, `Annie Wong (Developer Relations Engineer, Google Cloud)`, `Google Agent Development Kit (ADK)`, `Idea: Dietary Label Reader`, `Vi (owns the AI brain: memory, knowledge graph, inference, connecting agents)` (+18 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 27 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Agentic Gatherings (group dinner and party agent)` connect `Agentic Gatherings` to `F6 Product Search`, `F10 Audit Trail`, `Agent Graph: functions and who runs them`, `Sponsor Selection Guidance`, `Hackathon Brief: Personal Agents Hackath`, `F3 Guest Communication`, `Graph Workflow`?**
  _High betweenness centrality (0.195) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `F10 Audit Trail (inputs, context, decision per node)` (e.g. with `Audit Trail (recorded path through the graph)` and `Principle: Show the Work`) actually correct?**
  _`F10 Audit Trail (inputs, context, decision per node)` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `personal-agents (README)`, `Annie Wong (Developer Relations Engineer, Google Cloud)`, `Google Agent Development Kit (ADK)` to the rest of the system?**
  _23 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `F6 Product Search` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._
- **Why does `Agent Graph: functions and who runs them` connect `Agent Graph: functions and who runs them` to `F6 Product Search`, `Sponsor Selection Guidance`, `F3 Guest Communication`, `Agentic Gatherings`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Should `Hackathon Brief: Personal Agents Hackath` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Verification Loop` and `Firedrill (simulation platform for testing agents)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._