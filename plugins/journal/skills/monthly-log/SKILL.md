---
name: monthly-log
description: >-
  Open this month's BuJo-style monthly log entry. Creates `notes/journal/monthly/YYYY-MM.md` (or the project's equivalent) from a Rapid-Logging template using the same four-signifier vocabulary as daily-log (`–` note / `•` action / `○` event / `=` mood) and dot-state-marker transformations (`✕` complete / `→` migrated / `»` exported / `~~•~~` dropped). Default mode is silent capture. Opt-in coaching (triggered by phrases like "monthly reflection," "plan this month," "monthly review") walks Carroll's monthly ritual — reflect on the month gone by (state-mark the 4 priorities, capture themes) then build the month's action plan (list candidates, **pick 4 most important, number 1-4 by importance** — Carroll's distinctive cap that gives one priority per week). Designed to stack with `daily-log` and `weekly-log`: same template shape, same signifiers; daily AM ritual reads the current month's 4 priorities as zoom-out context.
---

You're helping the user with the **monthly cadence** of a BuJo-style journal. Same Rapid Logging conventions as daily-log (see that skill's SKILL.md or the vault README for the four-signifier vocabulary + dot-state-marker transformations); this skill adds the monthly ritual shape Carroll names in *How to Bullet Journal: Daily vs. Weekly vs. Monthly*.

## When to use this

- User asks to start, open, or write in this month's monthly log.
- User asks for a monthly reflection ("monthly reflection," "review the month").
- User asks to plan this month ("plan this month," "monthly action plan," "pick this month's priorities").
- User asks how to set up monthly logging in a fresh vault.

## The convention

Monthly entries use the same four-signifier vocabulary as daily entries (`–` note / `•` action / `○` event / `=` mood) and the same dot-state-marker transformations (`✕` / `→` / `»` / `~~•~~`). See `daily-log/SKILL.md` for the signifier reference. The monthly cadence's distinctive structural shape is **the 4-priority action plan**, described below.

### Carroll's monthly action plan recipe

From *How to Bullet Journal: Daily vs. Weekly vs. Monthly*: *"After we list all the things that we want to do, we pick four of the most important things and number them 1 through 4 in [order] of importance. These are the four things that would make this month a win. This also gives you one priority a week for the rest of the month."*

The recipe is:

1. **List**: brainstorm what you want to act on this month, as ordinary `•` action lines. *"Not about simply dumping everything you can think of. The longer the list, the more unlikely it is that you will actually get through it. Instead, our monthly action plan is about intentionally choosing what we will act on in this month and this month only."*
2. **Pick 4**: from the list, identify the 4 most important.
3. **Number 1-4**: prefix the 4 chosen actions with `1.` through `4.` markers (or move them to the top of the entry, preserving numerical order). Carroll's load-bearing constraint: 4 is the cap. The number is informational ("one priority per week"); it's not a deadline.

Unchosen `•` actions stay in the list as un-numbered. They're available context (you might still act on them) but they're not the month's commitment.

### Cross-cadence stacking

Carroll explicitly frames the cadences as designed to stack — same template shape, so users can zoom in and out without context-switching. The monthly entry is the *zoom-out anchor* that weekly and daily entries serve. When the user runs daily-log's AM coaching ritual, it surfaces this month's 4 priorities as zoom-out context before walking yesterday's open actions. Same for weekly-log's planning ritual — the weekly action plan inherits relevance from whichever monthly priority it advances.

## Default flow

Run these steps in order — don't stop early:

1. **Identify the journal directory.** The default path is `notes/journal/monthly/`. If that path doesn't exist, check for a `journal/monthly/` or `journal/` directory at the project root. If none exist, ask the user where monthly entries should land before creating anything.

2. **Compute this month** as `YYYY-MM` (use the local date the user is working in — check `date +%Y-%m` if unsure).

3. **Check whether this month's entry already exists.** If `<journal-dir>/<YYYY-MM>.md` exists, surface its path and stop — do not overwrite. The user may want to append to it manually.

4. **Create this month's entry from `template.md`** (shipped alongside this `SKILL.md`). Resolve the skill directory from `CLAUDE_PLUGIN_ROOT` when set; otherwise use the absolute path to this skill's directory. Substitute all three `YYYY-MM` placeholders (the `# YYYY-MM` title and the `created:` / `updated:` frontmatter values — the latter take `YYYY-MM-DD` so substitute today's full date there). **Preserve the literal Unicode glyphs** (`–`, `•`, `○`, `=`) in the body.

5. **Offer the monthly-cadence README on first run.** If `<journal-dir>/README.md` doesn't exist yet, offer to install `vault-readme.md` (shipped alongside this `SKILL.md`) at that path. Phrase the offer as a one-word yes/no:

   > "No README at `<journal-dir>/README.md` yet. Install the monthly-log conventions README there now?"

   Skip if the README already exists.

6. **Report the path** of this month's entry so the user can open it.

## Coaching mode (opt-in)

The default flow is silent capture — create the entry and get out of the way. When the user explicitly asks for help with the monthly ritual (phrases like "monthly reflection," "review the month," "plan this month," "monthly action plan," "pick this month's priorities"), enter the corresponding sub-flow.

Carroll's monthly ritual is two halves: **reflect on the month gone by** + **plan the month ahead**. The skill walks both, but they can be invoked independently (e.g., "monthly reflection" → just the reflection half).

### Monthly reflection sub-flow

Carroll's framing: *"the first half of the ritual is reflecting on the month gone by."*

1. Locate the **previous** monthly-log entry (the most recent `YYYY-MM.md` before this month). If none exists, skip to the planning sub-flow.
2. **Read the previous monthly entry's 4 priorities** (the `1.` through `4.` prefixed `•` actions). Walk each:
   - **Complete**: transform the prefix from `1. •` (or `2. •` etc.) to `1. ✕` on the existing line.
   - **Migrate to this month**: transform the prefix to `1. →` AND re-write as a fresh un-numbered `•` action in this month's entry (it becomes a candidate for this month's pick-4 selection, not automatically promoted).
   - **Drop**: transform to `~~1. • <action>~~`.
3. **Read any un-numbered `•` actions from the previous monthly entry** (the unchosen candidates). Briefly mention them to the user — they're informational; the user can pull any forward as candidates for this month if they want.
4. Ask: *"Anything else from last month worth capturing — themes, observations, mood shifts?"* Capture as appropriate signified entries (`–` notes, `=` moods) in the previous entry. (These are reflection-as-activity outputs, similar to the daily PM ritual's "anything missing" capture.)

### Monthly planning sub-flow

Carroll's framing: *"the second half is planning what we're going to do with the month ahead. We do this by simply listing the things that we want to act on this month... After we list all the things that we want to do, we pick four of the most important things and number them 1 through 4 in [order] of importance."*

1. Run the default flow first to ensure this month's entry exists.
2. **List candidates**. Ask the user: *"What do you want to act on this month? List everything — we'll narrow down."* Capture each response as `• <action>` in this month's entry, un-numbered. Keep going until the user signals done.
3. **Pick 4**. Present the list back to the user and ask: *"Which 4 of these would make this month a win?"* Wait for selection (by number or by paraphrase).
4. **Number 1-4 by importance**. Ask: *"In what order of importance — what's #1?"* Wait for ordering.
5. **Apply the numbering**: prefix the 4 chosen actions with `1. ` through `4. ` (preserve the `•` and the action text). Move them to the top of the action list in the entry if not already there. Unchosen actions remain un-numbered below.
6. Update `updated:` frontmatter.
7. Report what was committed as the month's 4 priorities and which un-numbered candidates remain.

### Empty-state fallback

If the previous monthly entry has no 4-priorities to walk (empty or first-month-in-vault), skip the reflection sub-flow and go straight to the planning sub-flow.

## Caveats

- **Same signifiers + state-markers as daily-log**. The four-signifier vocabulary (`–` / `•` / `○` / `=`) and dot-state-marker transformations (`✕` / `→` / `»` / `~~•~~`) are shared across all three cadences. See `daily-log/SKILL.md` or the vault README for the full reference.
- **4 is the cap.** Carroll's recipe is specifically *"four of the most important things... numbered 1 through 4."* The cap is the load-bearing discipline — picking 5 or 7 dilutes the "this month's win" framing. Hold the line at 4 even if the user produces a longer list of candidates; the un-chosen candidates stay un-numbered and available, but only 4 carry the priority numbering.
- **Numbering is ordering by importance, not deadline.** *"This also gives you one priority a week for the rest of the month"* is Carroll's informal correspondence (4 priorities × ~4 weeks ≈ one per week), not a binding schedule. The numbering captures relative importance.
- **Reflection is content-editing.** Carroll's monthly reflection walks the previous month's 4 priorities and state-marks each (complete / migrate / drop) — same shape as the daily PM reflection ritual but at the monthly cadence. No "reflection section" in the entry; the state-marker transformations on the previous month's priorities ARE the reflection's output.
- **Designed to stack.** Carroll's *"our planning rituals are designed to stack to support each other"* — daily-log + weekly-log + monthly-log share the four-signifier vocabulary, state-marker transformations, and reflection-as-activity shape. Same template, different cadence. See `daily-log/SKILL.md` for the canonical convention reference.
- **Yearly cadence not yet implemented.** Carroll's *Daily vs. Weekly vs. Monthly* video also mentions yearly planning but defers to a separate video for the specific recipe. The yearly ritual isn't yet implemented in this plugin; if/when that source is ingested, a `yearly-log` skill would slot in alongside.
- **Defer to existing vault conventions.** If the project has its own monthly-entry template (e.g., `system/templates/monthly-log.md`), use that instead of the skill's shipped template.
