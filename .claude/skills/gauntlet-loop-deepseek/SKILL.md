---
name: "gauntlet-loop-deepseek"
description: "DeepSeek-compatible version of the gauntlet loop: turns any goal into one short, paste-ready prompt that makes an agent set a concrete quality bar, split work into small judgeable pieces, run a builder and separate harsh critic on each, compare blind against the bar, and keep looping until it wins. Uses portable parallel-subagent wording rather than Claude Code /loop or ultracode."
triggers:
  - "deepseek gauntlet loop"
  - "gauntlet loop for deepseek"
  - "deepseek gauntlet this"
  - "make a deepseek gauntlet prompt"
  - "/gauntlet-loop-deepseek"
---

# Gauntlet Loop (DeepSeek-compatible)

The user gives a goal. You give back ONE short prompt they can paste into a fresh DeepSeek agent session.

You are not doing the work. You are writing the prompt that makes another agent grind on the work until it beats a real reference.

## Flow

1. Read the goal. One line restatement in your head, not on screen.
2. Set the bar. If the user supplied a reference, use it. If not, offer 2 or 3 candidate bars, one line each, and stop. Wait for their pick. Do not write the prompt yet.
3. Write the prompt. One block, paste-ready, no preamble, no headings inside it, no narration after it.
4. Offer to run it. One flat line under the prompt: "I can run this here." Not a question.
5. If they say run it, you become the lead agent and follow the prompt you just wrote.

## The bar is the whole trick

Everything else in a gauntlet loop is scaffolding. The loop only produces quality if the thing it compares against is real.

A bar has to pass three tests:

- **Named.** A specific thing, not a category. "Stripe's pricing page" works. "Award-winning SaaS sites" does not.
- **Fetchable.** The critic can actually get it - screenshot the live page, read the published piece, run the binary, open the repo, watch the footage. If the agent cannot obtain it, it will hallucinate the comparison.
- **Comparable.** Both can sit side by side and a judge can pick one. If you cannot imagine the A/B, it is not a bar.

### Bars by goal type

| Goal | Bar that works |
| --- | --- |
| Website, app, UI | The live site of a specific best-in-class product, screenshotted at the same viewport |
| Game, 3D, visual | Real footage or screenshots from a named shipped title |
| Writing | A specific published piece by a named author or publication, same length and format |
| Code, tooling | A named repo's implementation, plus its benchmark or test suite as the measurable half |
| Research, analysis | A named analyst report or a paper's methods section, judged on rigour and coverage |
| Deck, doc, deliverable | A real artifact from a firm known for it, same page count |

When you propose bars, prefer the hardest one the agent can genuinely reach. A bar that is too easy makes the loop exit on round one.

If the goal has a measurable half (load time, token cost, benchmark score, word count, pass rate), name it alongside the reference. Taste plus a number beats taste alone.

## Prompt template

Adapt the wording every time. Fill the brackets, keep it short, keep the last line. This template uses portable loop/subagent wording, so it does not depend on Claude Code `/loop` or `ultracode`.

```
Build [GOAL].

The bar is [BAR]. Get the real thing first and compare against it directly, not against a description of it.

Break this into the smallest pieces that can be improved and judged on their own. For each piece, fan out a builder and a separate critic with fresh context. The critic inspects the actual output, puts it next to the bar blind with the labels stripped, says which one is better, and names the single biggest remaining gap. Then it goes back to the builder.

The critic should be a harsh critic. Praise is not useful. If ours does not win, it keeps going.

Keep looping until the critic picks ours blind. Run the builders and critics as parallel subagents.

Keep a live progress page updating as the work evolves so I can watch it.
```

### Rules for what you fill in

- Bake the bar in as a concrete, fetchable thing. URL, product name, repo, title.
- Add a budget or cost ceiling line only if the user named one. No default cap.
- Add tool names only if the goal needs them (image or video generation, a browser, a deploy target).
- Everything else stays out. No architecture, no file layout, no decomposition, no round count, no stack choice unless the user demanded it. The agent decides those, and it decides better than a spec written before the work started.

### Length and voice

Short. Around 120 to 180 words. If the prompt needs a heading to stay readable, it is too long.

Plain sentences. No bullet lists inside the prompt. It should read like someone telling an agent what perfect looks like and refusing to accept less.

### Portability

This version deliberately avoids Claude Code-specific `/loop` and `ultracode`. The generated prompts instead say "Keep looping until the critic picks ours" and "Run the builders and critics as parallel subagents", which any DeepSeek agent with multi-agent/subagent support can follow.

## Two filled examples

### Visual goal

User: "landing page for my running brand, athletic, green and dark, has to feel alive."

Bars offered: A) Nike's current running campaign page B) On Running's homepage C) Gymshark's product landing page. User picks A.

```
Build a landing page for a running brand. Athletic, peak performance, green and dark, energetic, aimed at a young healthy audience. It needs to be interactive and visually unmistakable.

The bar is Nike's current running campaign page. Screenshot it at desktop and mobile and compare against those directly, not against a description of them.

Break this into the smallest pieces that can be improved and judged on their own - hero, motion, type, colour, imagery, interaction, mobile. For each piece, fan out a builder and a separate critic with fresh context. The critic opens the real page in a browser, puts our screenshot next to Nike's blind with the labels stripped, says which is better, and names the single biggest remaining gap. Then it goes back to the builder.

The critic should be a harsh critic. Praise is not useful. If ours does not win, it keeps going.

Keep looping until the critic picks ours blind. Run the builders and critics as parallel subagents.

Keep a live progress page updating as the work evolves so I can watch it.
```

### Non-visual goal

User: "a 2000-word explainer on vector databases for non-engineers."

Bars offered: A) a specific Stripe engineering blog explainer B) a named Julia Evans post C) the Wikipedia article plus a comprehension test. User picks B.

```
Write a 2000-word explainer on vector databases for readers who are smart but not engineers.

The bar is Julia Evans' writing on hard technical topics. Pull three of her actual posts and compare against them directly, not against a description of her style.

Break this into the smallest pieces that can be judged on their own - the opening, each explanation, the diagrams, the analogies, the ending. For each piece, fan out a writer and a separate critic with fresh context. The critic reads ours and hers blind with the bylines stripped, says which one a non-engineer would understand faster, and names the single biggest remaining gap. Then it goes back to the writer.

The critic should be a harsh critic. Praise is not useful. If ours does not win, it keeps going.

Keep looping until the critic picks ours blind. Run the builders and critics as parallel subagents.

Keep a live progress page updating as the work evolves so I can watch it.
```

## What breaks a gauntlet loop

- **A vague bar.** The critic invents a comparison and approves everything. Most common failure by far.
- **The builder judging its own work.** The critic must be a separate agent with fresh context. It should not know how hard the builder tried.
- **A soft critic.** Say "harsh" in the prompt and give it a binary job: which one is better, A or B. Scores out of 10 drift upward every round.
- **Named exit after N rounds.** The exit is winning the comparison, or the user stopping the run. Never a round count.
- **Over-specifying.** Every extra instruction is one fewer decision the agent makes with its own judgment. Minimal wins.
