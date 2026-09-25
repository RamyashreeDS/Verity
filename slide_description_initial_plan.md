Slide 1 — Verity

“Hi everyone, we’re Verity — a self-healing situational intelligence platform designed to figure out what’s actually happening around you, even when information online is messy, contradictory, or outdated.”

Keep this slide very short and immediately move into the problem.

Slide 2 — Intro / The problem

“Quick show of hands — who here knew that San Francisco was flooded yesterday?

And more importantly… Do you know what roads were actually affected?

Let’s try to look that up before driving into a million closed roads..”

Pause, then start revealing the screenshots.

“So I searched for it. And this is what I got.”

As the hectic images appear:

“I found social media posts, random maps, temporary street closures, videos, search summaries, and a bunch of information that may or may not even be related to the flooding.”

The presentation specifically frames the problem as finding which roads were closed after the San Francisco flooding.

Then reveal the final text boxes.

“And after digging through all of that, I finally got to something useful… except even that says the highway is ‘likely closed.’

So now I have information — but I still don't really have an answer.

And that's the problem we're trying to solve. Information about what's happening around us exists, but it's fragmented across different sources, updated at different times, and often contradicts itself.”

Then transition:

“What if instead of searching through all of this ourselves, we had an agent whose entire job was to continuously figure out the current state of the world for us?”

Slide 3 — Verity / Live Demo

“That’s Verity.”

Pause here before opening the actual product.

“Instead of giving you ten links to investigate, Verity gives you a single evolving view of what is happening, where it's happening, how it affects the surrounding area, and — most importantly — why it believes that information is true.”

During the demo:

“Here we can see events around the area — that could be flooding, a car accident, construction, a parade, a concert, or anything else that changes how people move through the city.”

Click an event.

“Each event isn't just a marker on a map. Verity keeps the individual claims behind it — when it happened, what areas are affected, its sources, when those sources were published, and whether the information is currently verified, disputed, or becoming stale.”

Then show evidence/confidence state.

“And instead of pretending everything has an arbitrary 87-percent confidence score, we expose the actual state of the evidence: reported, corroborating, verified, stale, or disputed.”

If your demo has the conflict injection/self-healing flow:

“Now here's where Verity becomes different from a normal aggregation dashboard. I'm going to introduce information that conflicts with what Verity currently believes.”

Trigger it.

“Verity detects that contradiction instead of silently choosing whichever source it saw last. It flags the state as disputed and starts investigating.”

Show the process.

“It searches for newer and independent evidence, compares timestamps and source provenance, and proposes an updated world state.”

Then state change:

“Once that correction passes validation, Verity updates the state — and records exactly why that decision was made.”

That directly demonstrates the features already called out in your deck: event summaries, affected-area mapping, contradiction detection, state changes, persistent history, and user reporting.

Slide 4 — Features

“So there are a few key ideas behind Verity.”

Rather than reading every bullet:

“First, Verity turns scattered information into structured events — what happened, where, when, and what sources support it.

Second, we connect those events to an interactive map so that we're not just telling you there was an accident or a flood — we're showing you what areas and roads are affected.

Third, we expose the agent's reasoning process. You can see when it detects contradictions, when information becomes stale, when it starts verifying something, and when its understanding changes.

And finally, the system keeps its history. If Verity changes a road from closed to open, that previous belief doesn't disappear. We know what changed, when it changed, and what evidence caused the change.”

Slide 5 — Sense: Nimble

The deck introduces Nimble as the sensing layer.

“The first part of our stack is Nimble, which acts as Verity's eyes.”

“Nimble searches and extracts live information from the web. Rather than relying on one search result, Verity can investigate multiple sources and retrieve the actual content behind them.”

“So if somebody reports that a highway is closed, Nimble can immediately look for transportation updates, government notices, local reporting, and other independent evidence.”

Transition:

“But gathering information isn't enough. Something still needs to understand what all those sources are actually saying.”

Slide 6 — Understand: Liquid LFM

The next layer in the deck is Liquid LFM.

“That's where Liquid AI's LFM comes in.”

“Liquid is the reasoning layer. It takes the information Nimble retrieves and converts it into structured claims.”

For example:

“Instead of keeping an entire article in context, we can reduce it to something like:
Highway 17 — status: closed — reported at 1:15 PM — source: transportation authority.”

“Liquid can then compare those claims and recognize things like: these two sources disagree, this information refers to an older update, or we're missing enough information to make a decision.”

Then emphasize:

“But there's one very important constraint: the language model does not get to decide reality by itself.”

Slide 7 — Validate & Determine World State

This slide represents the validation/world-state layer in the deck.

“Verity separates reasoning from authority.”

“Liquid can propose that the state should change, but deterministic code decides whether that change is allowed.”

“We check things like timestamps, source independence, whether the evidence actually refers to the same location and event, and whether there is newer contradictory evidence.”

“So the principle is simple: LLMs interpret. Code enforces.”

Then explain uncertain states:

“And importantly, Verity is allowed to say ‘I don't know.’ If two credible sources still disagree, the correct answer isn't to hallucinate certainty. The event stays disputed until we have enough evidence.”

Slide 8 — Full History: RawTree

RawTree is the full-history layer in the deck.

“The next challenge is memory.”

“An agent running for hours or days could accumulate hundreds of searches, articles, corrections, and tool calls. We don't want to keep shoving all of that back into the model every time it thinks.”

“So RawTree acts as Verity's long-term memory and flight recorder.”

“We store the evidence, previous world states, tool calls, contradictions, repair attempts, and outcomes there.”

“Liquid only receives the current state and the small portion of history that's relevant to the problem it's solving right now.”

Then hit the hackathon theme:

“That lets the agent operate over a long horizon without its context window continuously growing.”

Slide 9 — Health Monitor & Healing Loop

The deck explicitly dedicates this slide to the health monitor and healing loop.

Slow down here because this is probably your strongest technical slide.

“And this is the core of Verity: the self-healing loop.”

“Verity continuously monitors its own world state for signs that something is wrong.”

“That might be two credible sources contradicting each other. It might be a road status that hasn't been verified recently. It might be the agent repeatedly performing the same search without learning anything new.”

Then:

“When one of those conditions occurs, Verity doesn't immediately rewrite its state.”

“It goes through a bounded process: detect, diagnose, verify, validate, and then either commit or reject the repair.”

“If a repair later turns out to be worse than the state it replaced, we can roll back to the previous version.”

And your safety constraint:

“We also limit how many times Verity can try to repair the same issue. After a few failed attempts, it stops and marks the information as unresolved instead of spiraling into an endless agent loop.”

Then the key line:

“So when we say self-healing, we don't mean an LLM rewriting its own code. We mean an agent that can recognize when its understanding of the world is becoming unhealthy and deliberately gather the evidence necessary to repair it.”

Slide 10 — Dashboard / Closing

The final deck slide is the dashboard layer.

“And all of that comes back to this dashboard.”

“The user doesn't need to understand which model ran, how many searches happened, or which database query was executed.”

“They just need to know: What's happening? How does it affect me? And why should I trust this information?”

Then broaden the scope beyond disasters:

“And although flooding was our example, Verity isn't just an emergency-response tool. The exact same system works for car crashes, construction, parades, concerts, sporting events, protests, weather, or anything else that temporarily changes the world around us.”

Finish with:

Today, finding the most reliable news can mean opening ten tabs and trying to reconcile them yourself but with Verity, it’s right under your fingertip.
