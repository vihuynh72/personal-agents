# Agentic Graph and Workflow Guide

Source: Vi's notes from "Agentic AI Builder Lab with Google Cloud" (AI Camp SF, 2026-11-19), taught by Annie Wong, Developer Relations Engineer at Google Cloud. The lab used Google's open-source Agent Development Kit (ADK). We use the concepts for both our product design and our build orchestration; we are not required to use ADK.

## Core idea

A graph workflow abstracts a process into nodes and edges. It is more reliable than a pure multi-agent system, because the order of work is fixed by the graph instead of decided by agents at runtime. Start small with a single agent and tools, then move the process into a graph.

## Agent anatomy

An agent has a model (the brain), instructions, tools, and optional sub-agents. Sub-agents form a tree and give a pure multi-agent system.

Agent modes:

- Chat mode: the agent has full control, with swarming and handoffs. Default for multi-agent systems.
- Single turn mode: the agent is stateless and moves node to node in a workflow.
- Task mode: the agent loops with tools until the task is complete. This enables loop engineering.

## Node types

- Agent node: uses a model for generative work, for example proposing topics or writing a script.
- Function node: deterministic code, for example scanning trends or reading a backlog.

Use a function node whenever the step does not need judgment.

## Edge patterns

- Node to node: enforces sequential order.
- Fanout and fanin: run nodes in parallel, then a join node waits for the slowest result before continuing.
- Router: a condition that sends work to different sub-processes. It can be deterministic if/else or AI based.
- Loop: a task-mode agent keeps calling tools until the goal is met.

## Human in the loop

A human gate is a request-input node. The workflow suspends and waits indefinitely for the human, then resumes on the response. Use it for content direction choices, payment approvals and sensitive database actions.

## State, session and persistence

- State: key facts on a shared scratch note that every node in the graph can read and write.
- Session: the full raw conversation history for one thread.
- A persistent database is required to keep state across server crashes and long waits.

## Long-term memory

- A memory service summarizes conversations into distilled facts, consolidates and deduplicates them (a preference changing from black to red is updated, not duplicated), and searches by semantic similarity.
- Memory read happens in a before-model callback, so preferences load before the agent reasons.
- Memory write happens in an after-agent callback, saving a session summary.
- RAG ingests external data (chunk, embed, index) and is added as one more parallel fanout node.

## Long-running tools

A long-running tool wraps work that takes minutes or hours. The workflow suspends, and a completion signal sends a function response to resume it. In production use a cron job, scheduler or watcher instead of a polling loop.

## Verification loops

After an agent acts, add a check call that confirms the action happened, for example fetch the calendar event after creating it.

## MCP versus agent to agent

MCP connects an agent to external tools. Agent to agent is orchestration between agents. They are distinct patterns.

## How this maps to our project

| Guide concept | Agentic gatherings product |
|---------------|----------------------------|
| Fanout and fanin | Ask every invitee's agent for availability and preferences in parallel, join on the slowest reply |
| Function node | Calendar lookup, restaurant search, age check |
| Agent node | Reconcile preferences into a venue shortlist, draft the plan |
| Router | Dinner mode, party mode or host mode |
| Human gate | Organizer approves the plan; invitee accepts; yes or no at checkout |
| State | The gathering: people, constraints, candidate venues, decisions |
| Long-term memory | Each person's profile and feedback from past gatherings |
| Long-running tool | Waiting for invitees to respond while the laptop is closed |
| Verification loop | Confirm the reservation or order exists after booking |
| Audit trail | The recorded path through the graph, with the context each node used |
