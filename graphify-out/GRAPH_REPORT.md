# Graph Report - personal-agents  (2026-11-20)

## Corpus Check
- Corpus is ~2,368 words - fits in a single context window. You may not need a graph.

## Summary
- 91 nodes · 121 edges · 15 communities (6 shown, 9 thin omitted)
- Extraction: 82% EXTRACTED · 17% INFERRED · 1% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.82)
- Token cost: 147,419 input · 0 output

## Community Hubs (Navigation)
- Butler Shopping and Checkout
- ADK Graph Workflow Basics
- Human Gates and Persistence
- Profiles, Memory and Fanout
- Agentic Gatherings Concept
- Team Memory and Sponsors
- Stack and Form Factor
- Tools, MCP and Verification
- Voice and Accessibility
- Specificity versus Muse
- No Medical Advice
- Clothing Agent (rejected)
- Out-of-Stock Substitution (rejected)

## God Nodes (most connected - your core abstractions)
1. `Agentic Gatherings (group dinner and party agent)` - 16 edges
2. `Graph Workflow (nodes and edges)` - 13 edges
3. `Hackathon Brief: Personal Agents Hackathon (tokens&)` - 10 edges
4. `Brainstorm: 2026-11-20 Team Session` - 8 edges
5. `Sponsor Selection Guidance (pick two or three)` - 8 edges
6. `Personal Agent Profile (calendar, dietary restrictions, allergens, cuisine, age)` - 7 edges
7. `Host Mode` - 6 edges
8. `Long-Term Memory (memory service)` - 5 edges
9. `Challenge: Shopping Agent With an Audit Trail` - 5 edges
10. `Agent Anatomy (model, instructions, tools, sub-agents)` - 4 edges

## Surprising Connections (you probably didn't know these)
- `Cognee (open-source memory for agents)` --semantically_similar_to--> `Long-Term Memory (memory service)`  [INFERRED] [semantically similar]
  docs/hackathon-brief.md → docs/agentic-graph-guide.md
- `Firedrill (simulation platform for testing agents)` --conceptually_related_to--> `Verification Loop`  [AMBIGUOUS]
  docs/hackathon-brief.md → docs/agentic-graph-guide.md
- `Graphify Knowledge Graph (shared memory)` --references--> `personal-agents (README)`  [EXTRACTED]
  docs/brainstorm.md → README.md
- `Agent-to-Agent Privacy Concern` --conceptually_related_to--> `Agent to Agent (orchestration between agents)`  [INFERRED]
  docs/brainstorm.md → docs/agentic-graph-guide.md
- `Audit Trail (recorded path through the graph)` --semantically_similar_to--> `Audit Trail (context and steps behind each action)`  [INFERRED] [semantically similar]
  docs/agentic-graph-guide.md → docs/hackathon-brief.md

## Hyperedges (group relationships)
- **Agentic Gatherings Coordination Flow (profile, time check, preference check, approval, booking verification)** — docs_brainstorm_personal_agent_profile, docs_brainstorm_time_check, docs_brainstorm_preference_check, docs_agentic_graph_guide_human_gate, docs_agentic_graph_guide_verification_loop, docs_agentic_graph_guide_audit_trail [INFERRED 0.85]
- **Graph Workflow Edge Patterns** — docs_agentic_graph_guide_node_to_node, docs_agentic_graph_guide_fanout_and_fanin, docs_agentic_graph_guide_router, docs_agentic_graph_guide_loop [EXTRACTED 1.00]
- **Design Principles the Team Agreed On** — docs_brainstorm_action_not_chat, docs_brainstorm_human_yes_or_no, docs_brainstorm_butler_agent, docs_brainstorm_learn_from_feedback, docs_brainstorm_show_the_work, docs_brainstorm_kill_switch, docs_brainstorm_lid_closed_cloud_agent, docs_brainstorm_be_specific, docs_brainstorm_no_medical_advice, docs_brainstorm_domain_data [EXTRACTED 1.00]

## Communities (15 total, 9 thin omitted)

### Community 0 - "Butler Shopping and Checkout"
Cohesion: 0.14
Nodes (15): Idea: Butler Shopping Agent, Host Mode, Idea: Lifestyle Food Agent, Photon (texting app), Stripe Checkout, Amplitude + Statsig (agent analytics, flags, experimentation), Arcee AI (open-weight foundation models), Challenge: Shopping Agent With an Audit Trail (+7 more)

### Community 1 - "ADK Graph Workflow Basics"
Cohesion: 0.19
Nodes (4): Google Agent Development Kit (ADK), Agentic AI Builder Lab with Google Cloud (AI Camp SF, 2026-11-19), Agentic Graph and Workflow Guide, Annie Wong (Developer Relations Engineer, Google Cloud)

### Community 4 - "Agentic Gatherings Concept"
Cohesion: 0.31
Nodes (7): Add-Friend Mode (limited data access), Agentic Gatherings (group dinner and party agent), Dinner Mode, Luma (traditional events app; positioning reference), Open Questions (mode, demo action, data sharing, sponsors, owners, Senso eligibility), Idea: Party and Event Agent, Party Mode

### Community 5 - "Team Memory and Sponsors"
Cohesion: 0.25
Nodes (7): Graphify Knowledge Graph (shared memory), Vi (owns the AI brain: memory, knowledge graph, inference, connecting agents), Airbyte (open-source data integration), Cognee (open-source memory for agents), Firedrill (simulation platform for testing agents), Guild AI (build, evaluate, deploy agents), personal-agents (README)

### Community 6 - "Stack and Form Factor"
Cohesion: 0.33
Nodes (5): Brainstorm: 2026-11-20 Team Session, Claude, Gemini, Vercel (front end only), Judging (no published criteria)

### Community 9 - "Voice and Accessibility"
Cohesion: 0.67
Nodes (3): Idea: Accessibility Agent, Deepgram (speech), Idea: Voice-Only Personal Agent

## Ambiguous Edges - Review These
- `Verification Loop` → `Firedrill (simulation platform for testing agents)`  [AMBIGUOUS]
  docs/hackathon-brief.md · relation: conceptually_related_to

## Knowledge Gaps
- **27 isolated node(s):** `personal-agents (README)`, `Annie Wong (Developer Relations Engineer, Google Cloud)`, `Google Agent Development Kit (ADK)`, `Luma (traditional events app; positioning reference)`, `Muse (existing generic agent)` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 34 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Agentic Gatherings (group dinner and party agent)` connect `Agentic Gatherings Concept` to `Butler Shopping and Checkout`, `ADK Graph Workflow Basics`, `Human Gates and Persistence`, `Profiles, Memory and Fanout`, `Stack and Form Factor`, `Tools, MCP and Verification`, `Audit Trail`?**
  _High betweenness centrality (0.324) - this node is a cross-community bridge._
- **What connects `personal-agents (README)`, `Annie Wong (Developer Relations Engineer, Google Cloud)`, `Google Agent Development Kit (ADK)` to the rest of the system?**
  _27 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Butler Shopping and Checkout` be split into smaller, more focused modules?**
  _Cohesion score 0.13970588235294118 - nodes in this community are weakly interconnected._
- **Why does `Graph Workflow (nodes and edges)` connect `ADK Graph Workflow Basics` to `Human Gates and Persistence`, `Profiles, Memory and Fanout`, `Agentic Gatherings Concept`, `Tools, MCP and Verification`, `Audit Trail`?**
  _High betweenness centrality (0.207) - this node is a cross-community bridge._
- **Why does `Brainstorm: 2026-11-20 Team Session` connect `Stack and Form Factor` to `Human Gates and Persistence`, `Agentic Gatherings Concept`, `Team Memory and Sponsors`?**
  _High betweenness centrality (0.151) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Verification Loop` and `Firedrill (simulation platform for testing agents)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._