# Verity — Speaker Script

Long Horizon Agents Hack · San Francisco · Sep 25, 2026
12 slides. Target: about 4½ minutes of speaking plus a 1-minute live demo (slide 4). Timings are per slide. If you need to hit 4 minutes total, cut the bracketed lines first, then shorten slides 10 and 11 to one sentence each.

Slide map: 1 Verity · 2 The problem · 3 The idea · 4 Live demo · 5 How it works · 6 Memory design · 7 How memory is updated and discarded · 8 The proof · 9 Memory & token utilization (live page) · 10 Trust · 11 The stack · 12 Closing

Before you start: have the app open on `http://localhost:8000` in **Live** mode with the speed set to **1 min / s**, the report box pre-filled, and the `/memory` page open in a second tab. If you want big numbers on the memory page, press **Replay last week** at 1 hour / s about three minutes before you go on; it reaches the full week in under three minutes.

---

## Slide 1 — Verity (0:15)

"Hi everyone, we're **Verity**.

Verity is a self-maintaining agent that knows what's actually happening on the streets of a city — and it can keep doing that for days, because it forgets what no longer matters.

Let me start with why that's hard."

---

## Slide 2 — The problem (0:40)

"Quick show of hands — who here knew San Francisco flooded yesterday?

More importantly: do you know which roads were actually affected? Let's say you try to look it up before driving.

*(advance through the fragments one by one)*

You get a Reddit thread asking the same question. A news story that says 'low-lying streets.' A government dataset with 4,600 rows and no map. A video with no location. A search summary that says 'several roads may be impacted.'

And after ten tabs, the best answer you get is: *'the highway is likely closed.'*

So you have plenty of **information** — but you still don't have an **answer**. It's fragmented across sources, updated at different times, and it contradicts itself."

---

## Slide 3 — The idea (0:30)

"So what if, instead of searching through all of that yourself, you had an agent whose entire job was to continuously maintain the current state of the world for you?

Instead of ten links, Verity gives you one evolving view: what is happening, where, whether cars still get through, until when — and why it believes that. Every event carries its evidence: unconfirmed, corroborated, verified, or cleared.

And here's the catch that makes this a long-horizon problem: this agent has to run for **days**, not minutes. Most agents drown in their own history. But road events are perfect for this — they **expire**. A farmers market ends at 2 p.m. A parade clears. A flood recedes.

So the core of Verity isn't the scraping. It's an agent that remembers active events, forgets expired ones, and keeps its context small no matter how long it runs."

---

## Slide 4 — Live demo (1:00, switch to the app)

"Let me show you. *(switch to the browser)*

This is San Francisco right now. Red segments are fully blocked. Orange means some lanes are closed. These come from the city's official closure permits.

Now I'm going to act as a random person on social media. *(type or use the pre-filled report)* 'Protesters are blocking Market St at 5th right now.' Send.

Watch the log: our on-device Liquid model reads that sentence and extracts the street, the cross street, and whether it's blocked — in about three seconds. And there it is on the map — **grey and dashed**, because one tweet is a rumor, not a fact. Confidence 0.3.

Now I click **Verify**. Verity uses Nimble to search the web for independent evidence. *(pause)* It found matching pages — confidence jumps to 0.86, and the segment turns red. It's now a confirmed closure, and Verity has generated a shareable alert card.

Finally, the world changes. *(send the 'reopened' example)* 'Market St at 5th has reopened.' Verity clears the event from the map — but it doesn't delete anything. The whole history is in the ledger. *(type 'Market St' in Recall)* If I ask 'has Market St closed before?', the answer comes back from a SQL query — not from the model's context.

*(switch back to the slides)*"

---

## Slide 5 — How it works (0:30)

"Under the hood, it's one loop that runs every few minutes, and every cycle starts from a **compact state snapshot** — never from the history.

**Sense**: Nimble and the official feed bring in new information.
**Understand**: Liquid AI's LFM2.5 turns free text into a structured event, on the laptop, in about three seconds. No article ever stays in context — one short line does.
**Resolve**: we geocode to real street segments and merge reports about the same block.
**Verify**: a lone social post triggers an independent web check.
**Forget**: expired events are retired, stale rumors decay, and anything over the cap gets compacted into a digest.
**Publish**: the map, the ledger in RawTree, and an alert card from FLUX.

One principle runs through all of this: **LLMs interpret, code enforces.** The model proposes claims. Deterministic rules decide what enters the world state and what gets forgotten."

---

## Slide 6 — Memory design (0:30)

"This is the part built for the hackathon's theme. Verity has four tiers of memory, and **only one of them ever enters the model's context**.

Tier 0 is every raw page and post — hashed for dedup, stored in RawTree, never in context.
Tier 1 is the event ledger — every version of every event. The model only reaches it through SQL.
Tier 2 is digests — one line per retired event, recalled only on demand.
Tier 3 is the working state: the active events, one line each, capped at about four thousand tokens. That's the only thing the planner ever sees.

And the forgetting rules on the right are explicit, in code, and visible in the agent's log — not something the model decides on its own."

---

## Slide 7 — How memory is updated and discarded (0:40)

"Let me walk one report through that memory.

At time zero, the text is hashed. If we've seen it before, it's dropped before it costs a single token.

Three seconds later, the Liquid model extracts the event. The article is gone; one 25-token line enters the working state at confidence 0.3 — because a social post has a trust prior of 0.3.

A minute later, Nimble finds a news page about the same block. Sources combine as independent evidence — one minus the product of the misses — so 0.3 and 0.8 give us 0.86. That's above our 0.7 threshold, so the event becomes active.

Two hours later, a trusted source says 'reopened'. The event is cleared: a one-line digest is written and it leaves the context. Its history stays in the ledger.

*Or* — nobody confirms it. Then confidence decays 0.15 every hour: 0.3, 0.15, and below 0.2 it's dropped. A rumor nobody backs up is forgotten in about an hour.

The six numbers at the bottom are the entire policy: trust priors per source, the confirmation threshold, a 30-minute grace after a scheduled closure ends, the decay rate, the drop floor, and a hard 4,000-token cap on the working state.

And nothing is ever deleted — every create, merge, verify and retire is a row in RawTree with its reason. Only the **context** forgets."

---

## Slide 8 — The proof (0:30)

"Does it actually work over a long horizon? We replayed one real week of San Francisco closures, hour by hour — 168 cycles.

The blue line is what Verity sends to the model every cycle. It peaked at **1,885 tokens** and stayed flat all week.

The red line is what a naive agent that appends every observation would be carrying: **41,000 tokens by day seven**, and still climbing.

Over that week, 184 events were created and 152 were forgotten — about 32 active at any moment. The context tracks the *present*, not the past."

---

## Slide 9 — Memory & token utilization, live (0:40)

"That chart wasn't made for the slides. It's a page in the product, and it updates every cycle. *(switch to the `/memory` tab if time allows; otherwise stay on the slide)*

Top row, four numbers. On the left, what the model actually sees right now — about eleven hundred tokens, with a bar showing we're using **28 percent of our 4,000-token cap**. Next to it, the red number: what a naive agent that appends every observation would be carrying — 46,000 tokens and climbing. The green number is the ratio: **41 times smaller**, meaning 97.6 percent of everything we've observed never gets sent to the model. And the orange number: 165 events forgotten so far, with about four thousand context tokens reclaimed.

Below that is the same curve over time — blue flat, red rising — with a dashed line for active events. Notice the blue line tracks the dashed line, not the red one: our context scales with **what's happening now**, not with how long we've been running.

Then the four tiers with live counts: how many raw documents are sitting in RawTree, how many ledger versions, how many digests — and the one number that matters for the model, the working state.

The table in the middle is the discard ledger: every rule that fired — expired, decayed, cleared, compacted — how many events it removed, how many context tokens it freed, and how many digest tokens were kept *outside* the context.

And the two tables at the bottom are the receipts. On the left, every active event with its cost: about **25 tokens in context** versus **260-plus tokens of raw source** — that's the compression happening per event. On the right, the last sixty things Verity forgot, each with a timestamp, the rule, and the reason.

*(if the replay is running: 'You can watch the forgotten count climb while the context bar stays put.')*

So when we say memory-efficient, this is what we mean: every token is accounted for, and every forgotten event is explained."

---

## Slide 10 — Trust, not vibes (0:25)

"A quick word on confidence, because we didn't want a made-up 87 percent.

Confidence is the state of the evidence. Government feeds start at 0.95, news at 0.8, a single social post at 0.3. Independent sources combine; they're never averaged. Nothing shows as active below 0.7 — it's drawn grey and dashed instead.

And Verity is allowed to say 'I don't know.' If nobody corroborates a rumor, it decays and is dropped. There's no silent overwrite — every change is a ledger row with a reason. These are real lines from the agent's log."

---

## Slide 11 — The stack (0:25)

"Each sponsor tool has exactly one job, and you saw every one of them in the demo.

**Nimble** is the eyes — live web search and independent verification.
**Liquid AI's LFM2.5** is the brain, running on-device inside the agent process. No API, no model server, about three seconds per extraction.
**RawTree** is the long-term memory — schemaless ingest, SQL over HTTP. Recall is a query, not context.
**FLUX** from Black Forest Labs is the visual layer — one alert card per confirmed closure, clearly labeled as an illustration.

Plus the city's open data for ground truth and geocoding. Adding a new city means adding sources, not changing the agent."

---

## Slide 12 — Closing (0:20)

"Today, finding the most reliable answer means opening ten tabs and reconciling them yourself.

With Verity, it's right under your fingertip.

Floods were our example — but the same agent handles crashes, construction, parades, protests, strikes — anything that temporarily changes the world around you.

Thank you. We're happy to take questions."

---

## Likely questions and short answers

**"How accurate is the extraction from a 2.6B model?"**
Good on clean reports; noisier on long news pages, where it sometimes picks up roads outside SF. That's why extraction output never becomes truth on its own — it enters at the source's trust prior and needs corroboration to show as active.

**"Why not just use a bigger context window?"**
Cost and reliability. A growing transcript gets slower and more expensive every cycle, and stale facts sit next to fresh ones with equal weight. A flat working state plus SQL recall keeps the model's input small and current, and the same design works whether the agent runs for an hour or a month.

**"What happens when the working state hits the 4K cap?"**
The lowest severity × confidence events are folded into one-line digests first — partial-lane construction permits before full closures, low confidence before high. They stay queryable in RawTree.

**"Is the Nimble verification rigorous?"**
It's a first pass: it looks for independent pages that mention the street and a closure. For production we'd add timestamp checks and source independence scoring — the confidence model already has the slot for it.

**"Can it handle contradictions?"**
Today: a trusted 'reopened' report clears an event and the prior belief stays in history. Full disputed-state handling — two credible sources disagreeing — is the next step, and the ledger design is built for it.
