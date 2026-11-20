# Agentic Gatherings

A personal agent that feeds you and your friends. You send one text. It does the rest.


## The problem

You text five friends: "Dinner at my place Saturday?"

One friend is vegan. One has a peanut allergy. One is out of town. Now you are the coordinator. You collect the answers. You plan a menu that works for each person. You read ingredient labels in three stores. Then someone cancels and you start again.

Buying food for one person is the same problem in a smaller size. Each label is a small test.

An AI that only chats does not help. You still do the shopping.

## What the agent does

**It learns about you without a questionnaire.** A new person gets one question at most. Or connect Google, and it learns from your receipts and calendar.

**It shops for you.** Text "get me coffee". The agent finds real products from real stores. It reads each ingredient list and compares it with what you avoid. It ranks by safety first, then your preferences, then price per ounce. No sponsored ranking.

**It knows the difference between cooking and ordering.** "I want to cook spaghetti" gives you groceries. "What's for dinner" gives you prepared food.

**It tells you why.** Each item has a reason. If the agent cannot confirm an ingredient, it says "needs confirmation". It does not tell you an item is safe when it does not know.

**It asks before it spends.** You get one page with the items, the shipping, the tax and the total. You press one button to pay. After your first order you can turn on autopay with a spending limit.

**It plans with other people's agents.** For a group dinner, your agent asks each guest's agent two things: what to avoid, and when the guest is free. A guest's agent shares only that. It does not share the reason. The agents then agree on a menu with something for each person.

**It remembers.** A day after your order arrives, the agent asks how it was. Your answer changes what it picks next time. A newer statement replaces an older one. An allergy is different: only you can remove it.

**It keeps a record.** Each decision is in an audit trail: what the agent knew, what it chose, and why.

## Why this matters

For a person with an allergy or a strict diet, shopping is slow and has risk. This agent reads the labels and shows its work. A host stops being the coordinator. The agent asks you less each time.

## Sponsor technology in our stack

| Technology | What it does here |
|---|---|
| **Senso** | The trusted context layer. Product and ingredient data is in a Senso knowledge base. The agent searches it for each product it picks. Before checkout, Senso fact-checks the agent's claims. A conflict removes the item. |
| **Firedrill** | Our test partner. A simulated shopper with a severe peanut allergy pushed the agent for the cheapest option. Each run found a real bug. We fixed it and ran again until the agent passed. |
| **Cognee** | Memory for guest profiles and calendar availability. |
| **Airbyte** | Syncs calendar free and busy times. |
| **Persona** | Sandbox account connected. The age check before checkout is the next step. |

We also use Claude for careful reasoning, Gemini for fast decisions, Stripe for payment, Photon for iMessage, Bright Data for store pages, and Railway for hosting.

## Try it

- **Chat in a browser:** https://personal-agents-production-81468651.up.railway.app/try (type your phone number, then ask for something)
- **The app:** https://personal-agents-production-81468651.up.railway.app/app
- **Test card:** 4242 4242 4242 4242

## What is real today

Real: the conversation, the products, the ingredient checks, the Senso checks, the order page and the Stripe payment in test mode.

Simulated: the last step, where an order goes to the retailer. Our agent completes a checkout in a cloud browser on a store that we host. Walmart has an official gateway for approved agents. That is our production path.

The conversation in the app is a guided walkthrough. The conversation by text and at `/try` is the live agent.

Setup and more detail: `docs/submission-notes.md`.
