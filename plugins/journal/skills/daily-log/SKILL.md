---
name: daily-log
description: >-
  Open today's BuJo-style daily journal entry. Creates `notes/journal/daily/YYYY-MM-DD.md` (or project equivalent) from a Rapid-Logging template with `–` note / `•` action / `○` event / `=` mood signifiers and dot-state-markers (`✕` complete / `→` migrated / `»` exported / `~~•~~` dropped). Default mode is silent capture. Opt-in coaching — triggered by phrases like "morning reflection," "reflect on today," "wrap up the day," "close out today" — walks Carroll's daily reflection ritual: AM walks open `•` actions from the previous entry with carry-forward / migrate / delegate / drop branching (biased by stated energy state) and surfaces weekly+monthly context if those entries exist; PM walks today's open actions with mark-complete / migrate / delegate / drop, then captures anything missed. Designed to stack with `weekly-log` and `monthly-log`. Use when the user asks to open today's journal, add to the daily log, do a morning or evening reflection, or set up daily logging in a fresh vault.
---

You're helping the user with the **daily cadence** of a BuJo-style journal. The convention follows Ryder Carroll's Bullet Journal Method: symbol-only structure, no section headers, continuous capture throughout the day, with morning and evening reflection rituals that edit the log in place rather than appending to it. This skill is part of the `journal` plugin's three-cadence stack (`daily-log` + `weekly-log` + `monthly-log`); the cadences share signifier vocabulary, state-marker transformations, and reflection-as-activity shape, and the daily AM ritual reads the weekly and monthly entries as zoom-out context.

## When to use this

- User asks to start, open, or write in today's journal.
- User asks to "add to the daily log" or similar.
- User asks for a morning or evening reflection.
- User asks how to set up daily logging in a fresh vault.

## The convention

Four signifiers — use the literal Unicode glyphs at the start of each entry line:

- `–` (en dash, U+2013) note — observations, facts, things to remember
- `•` (bullet, U+2022) action — tasks, things to do
- `○` (white circle, U+25CB) event — meetings, calls, things that happened or will happen
- `=` mood — how you felt; the `=` shape is a prompt to think causally ("our feeling is the result of something")

Don't substitute Markdown list markers (`-`, `*`) for the BuJo glyphs — they render as a uniform bullet list and collapse the visual distinction the symbols are supposed to carry. Carroll's signifiers are **content-typed**: a feeling goes on a `=` line, a task goes on a `•` line, regardless of where in the day it's captured.

### Chaining via indentation

Indent child bullets under a parent event to give the event context. This is Carroll-attested as the structural chaining mechanism:

```
○ Met with Alice about the migration plan
  = Anxious about the timeline
  – Three-week ramp is tighter than I expected
  • Draft pushback email by Thursday
```

### Dot-state-marker transformations

Carroll's action dot has multiple states beyond open/closed. The state-marker is a single-character replacement of the `•` prefix on the **existing line** — don't add a new line, change the prefix on the existing entry. The whole point is the state-evolution of one action.

- `•` open action (initial state)
- `✕` (U+2715) completed — *"X marks the spot"*
- `→` (U+2192) migrated forward to a future daily/weekly/monthly log entry (or backward to a longer-cadence log)
- `»` (U+00BB) migrated outside the notebook (to a digital task manager, calendar, etc.)
- `~~• action~~` no longer relevant — markdown strikethrough on the whole line, since pure-Unicode dot-with-line-through isn't a common glyph

State-marker transformations are how reflection writes its output into the log without adding new content: the action stays in place, only its prefix changes. When migrating forward, the original action's dot becomes `→` AND the action is re-written as a fresh `•` in the destination entry — the re-write is the friction Carroll explicitly designs in.

### Migration

Open `•` actions that don't get done today get rewritten by hand into a future day's entry, AND the original action's dot becomes `→` in the source entry. Manual; the friction is intentional — re-writing forces a decision about whether the task is still worth doing.

### Cross-cadence stacking

Carroll explicitly frames the cadences as designed to stack — same template shape across daily/weekly/monthly, so users can zoom in and out without context-switching. The daily entry is the *zoom-in leaf*; the weekly and monthly entries are zoom-out anchors that the daily AM ritual reads as context. Each daily entry's actions should ideally advance the current week's plan, which should advance one or more of the current month's 4 priorities.

If `weekly-log` and `monthly-log` aren't set up yet, the daily cadence still works standalone — the AM ritual gracefully skips the cross-cadence reads when those files don't exist.

## Default flow

Run these steps in order — don't stop early:

1. **Identify the journal directory.** The default path is `notes/journal/daily/`. If that path doesn't exist, check for a `journal/daily/` or `journal/` directory at the project root. If none exist, ask the user where daily entries should land before creating anything.

2. **Compute today's date** as `YYYY-MM-DD` (use the local date the user is working in — check `date +%F` if unsure).

3. **Check whether today's entry already exists.** If `<journal-dir>/<today>.md` exists, surface its path and stop — do not overwrite. The user may want to append to it manually.

4. **Create today's entry from `template.md`** (shipped alongside this `SKILL.md`). Resolve the skill directory from `CLAUDE_PLUGIN_ROOT` when set; otherwise use the absolute path to this skill's directory. Substitute all three `YYYY-MM-DD` placeholders (the `# YYYY-MM-DD` title and the `created:` / `updated:` frontmatter values) with today's actual date. **Preserve the literal Unicode glyphs** (`–`, `•`, `○`, `=`) in the body — do not substitute ASCII equivalents.

5. **Offer the daily-cadence README on first run.** If `<journal-dir>/README.md` doesn't exist yet, offer to install `vault-readme.md` (shipped alongside this `SKILL.md`) at that path. The README documents the signifiers, dot-state-markers, reflection ritual, and cadence-stacking design for the human reader of the vault. Phrase the offer as a one-word yes/no:

   > "No README at `<journal-dir>/README.md` yet. Install the daily-log conventions README there now?"

   Skip the offer if the README already exists.

6. **Report the path** of today's entry so the user can open it.

## Coaching mode (opt-in)

The default flow is silent capture — create the entry and get out of the way. When the user explicitly asks for help with the reflection ritual (phrases like "morning reflection," "reflect on today," "wrap up the day," "close out today"), enter the corresponding sub-flow.

Carroll's reflection ritual is **content-editing, not content-adding**: morning reflection pulls open actions from the previous entry forward into today; evening reflection state-marks today's actions (complete / migrate / drop) and captures anything missed. The coaching sub-flows walk the user through this ritual structure, not a single-question prompt. **Do not invoke a coach sub-flow on a plain request to open today's journal** — coaching is opt-in, not opportunistic.

### Grounded in Carroll's own teaching

The AM/PM sub-flows below are grounded in two Carroll sources in the vault:

- **Mechanical ritual structure** (carry-forward / mark-complete / migrate / delegate / drop branching) is from *Bullet Journal in 5 Minutes a Day for Busy People* (`sources/normalized/web/videos/bullet-journal-in-5-minutes-a-day-for-busy-people.md`).
- **Energy-planning reframe** (the right answer for each open action depends on today's capacity, not a fixed rule) is from *How to Bullet Journal: Daily vs. Weekly vs. Monthly* (`sources/normalized/web/videos/how-to-bullet-journal-daily-vs-weekly-vs-monthly.md`): *"daily planning can be used not only to plan our day, but also our energy. When you sit down in the morning to map out your day, you get a chance to see how you're feeling and respond accordingly. If you realize it's going to be a big day, but you have little energy, maybe the first thing you do is delegate something or postpone something."*
- **Cross-cadence stacking** is also from *Daily vs. Weekly vs. Monthly*: the daily AM ritual reads the current week and month entries as zoom-out context.

### AM reflection sub-flow

1. Run the default flow first to ensure today's entry exists.
2. **Surface longer-horizon context** (cross-cadence read; skip silently if the files don't exist):
   - Compute the current ISO week as `YYYY-Www` (e.g., `2026-W20`) — use `date +%G-W%V`. Read `notes/journal/weekly/<YYYY-Www>.md` if it exists; surface its action plan to the user.
   - Compute the current month as `YYYY-MM`. Read `notes/journal/monthly/<YYYY-MM>.md` if it exists; surface the 4 priorities (the `1.` through `4.` prefixed `•` actions).
   - Frame: *"This week's plan: ... This month's priorities: ... Today's actions should ideally advance these."* Keep the framing one or two sentences — context, not interrogation.
3. **(Optional) Energy state check.** If the user's coaching invocation included an energy qualifier (e.g., "morning reflection — low energy day," "feeling drained," "big day, low capacity"), capture it and bias step 4's per-item branching:
   - **low energy** → ask "delegate or migrate?" first per item; "carry forward as-is" is the fallback.
   - **high energy** / not specified → ask "carry forward?" first per item; "delegate or migrate" is the fallback.
   - This is the operationalization of Carroll's *"daily planning can be used not only to plan our day, but also our energy"* reframe.
4. Locate the **previous** daily-log entry — the most recent `YYYY-MM-DD.md` before today. If none exists (fresh vault or first entry in a while), skip step 5 — go straight to step 6.
5. **Read the previous entry and list open `•` actions** — i.e. lines starting with `•` whose prefix has NOT been transformed to `✕` / `→` / `»` / strikethrough. Present each to the user and ask per item: *carry forward to today / migrate to a future day / delegate / drop?* (Per the energy state from step 3, bias which branch you ask about first.)
   - **carry forward**: append `• <action>` to today's entry AND transform the prefix in the previous entry from `•` to `→` to mark it migrated.
   - **migrate to a future day**: ask which day. Append `• <action>` to that day's entry (creating the entry from template if it doesn't exist), AND transform the previous entry's prefix to `→`.
   - **delegate**: prompt for one-line context (who/where), capture as `– delegated to <X>: <action>` on today's entry, AND transform the previous entry's prefix to `»` (migrated outside the notebook).
   - **drop**: transform the previous entry's prefix to `~~• <action>~~` (markdown strikethrough) to mark no-longer-relevant.
6. Ask: *"Any other actions for today that come to mind?"* Capture each as a fresh `• <action>` in today's entry.
7. Update the `updated:` frontmatter field of today's entry to today's date if it isn't already.
8. Report what was added to today's entry, what was state-marked in the previous entry, and which weekly/monthly priorities the user touched.

### PM reflection sub-flow

Carroll's evening ritual, from *Bullet Journal in 5 Minutes a Day for Busy People*: *"at the end of the day reflect on your daily log first you want to update it. Mark any actions that you've taken as complete... for the actions that remain incomplete now is the time to decide if they're still worth doing... now's a good time to figure out what to delegate or what to eliminate... look over the whole day and if you feel like there's anything missing now's a good time to write it down."*

1. Locate today's entry. If it doesn't exist, ask whether to create one — the user may have skipped capture today, in which case the body-walk-through step has nothing to read.
2. **Read today's entry and list open `•` actions**. Present each to the user and ask per item: *mark complete / migrate to a future day / delegate / drop?*
   - **complete**: transform the prefix from `•` to `✕` on the existing line.
   - **migrate**: ask which day to migrate to. Append `• <action>` to that day's entry (creating the entry from template if it doesn't exist), AND transform today's prefix from `•` to `→`.
   - **delegate**: prompt for one-line context (who/where), append a `– delegated to <X>: <action>` note to today's entry, AND transform the original `•` to `»`.
   - **drop**: transform the prefix to `~~• <action>~~` (markdown strikethrough).
3. Ask: *"Anything missing from today that should be captured before bed?"* Capture each as the appropriate signified entry (`–` note, `•` action, `○` event, `=` mood) in today's entry.
4. Update the `updated:` frontmatter field of today's entry to today's date.
5. Report the state-marker changes and any new entries.

### Empty-state fallback

If the previous-entry walk (AM) or today-entry walk (PM) finds no open `•` actions, skip the per-item dialogue and go straight to the catch-all question:

- **AM**: *"No carry-forward items from the previous entry. Any actions for today that come to mind?"* (Still surface weekly/monthly context from step 2 if those files exist — the zoom-out anchors are useful even when there's no previous-entry walk.)
- **PM**: *"No open actions to state-mark. Anything from today worth capturing before bed?"*

The fallback keeps the ritual structure intact while honoring sparse-day reality.

## Caveats

- **Preserve literal glyphs.** The template uses `–` (en dash), `•` (bullet), `○` (white circle), `=` (equals). Don't normalize these to ASCII when copying — the visual distinction is the point.
- **State-marker glyphs.** `✕` (U+2715) for complete, `→` (U+2192) for migrated forward, `»` (U+00BB) for migrated outside notebook. Markdown strikethrough (`~~...~~`) for "no longer relevant" since pure-Unicode dot-with-line-through isn't a common glyph.
- **State-marker transformations live in the source entry, not as new lines.** When marking an action complete or migrated, edit the original `•`-prefixed line in place. Adding a new line for the state-change defeats the design — Carroll's whole point is that the dot's evolution IS the record.
- **No positional bookends.** Earlier versions of this skill had AM/PM `=` mood-equals bookends at the top and bottom of each entry. Removed 2026-05-12 — that hybrid combined Carroll's per-line `=` mood signifier with the *chapter-level* "intention" concept from a separate Carroll source, producing a daily AM/PM mood-bookend that isn't actually Carroll-attested. The Carroll-pure shape is freeform Rapid Logging with reflection-as-activity.
- **Cross-cadence reads are graceful-fallback.** Steps 2 of the AM sub-flow reads weekly and monthly entries if they exist. If they don't (fresh vault, user hasn't set up the longer cadences yet), skip silently — daily-log works standalone. Don't prompt the user to set up the other cadences; that's their decision.
- **Capture layer only.** This skill covers the per-day capture page and the morning/evening reflection rituals. Cross-day linking, chapter-level intention pages, and BuJo's broader processing layer (Collections, Index, future log) are out of scope. Monthly migration and weekly review are covered by sibling skills `monthly-log` and `weekly-log`.
- **Defer to existing vault conventions.** If the project has its own daily-entry template (e.g., a `system/templates/daily-log.md` or similar), use that instead of the skill's shipped template. The shipped one is the default for fresh vaults, not an override for established ones.
- **Frontmatter is intentionally minimal.** The shipped template has only `created` and `updated` dates so it slots into any vault. If the project's other notes carry richer frontmatter (e.g., `related_concepts`, `source_refs`), extend the entry to match — but don't bake project-specific keys into the shared template.
- **Coaching is opt-in.** A plain "open today's journal" doesn't trigger reflection coaching. The user has to ask for a reflection explicitly — the BuJo register is freeform capture, and unrequested rituals subtract from that.
