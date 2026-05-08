---
name: daily-log
description: Open today's BuJo-style daily journal entry. Creates `notes/journal/daily/YYYY-MM-DD.md` (or the project's equivalent) from a Rapid-Logging template with `–` note / `•` action / `○` event / `=` mood signifiers and AM/PM mood-equals bookends. Default mode is silent capture. Opt-in coaching (triggered by phrases like "set my intention," "morning prompt," "reflect on today," "wrap up the day," "close out today") asks one question and writes the answer onto the appropriate bookend — day-of-week prompt for AM, body-aware question generated from today's captures for PM. Use when the user asks to open today's journal, add to the daily log, set their morning intention, do an evening reflection, or set up daily logging in a fresh vault.
---

You're helping the user with a BuJo-style daily journal. The convention follows Ryder Carroll's Bullet Journal Method: symbol-only structure, no section headers, continuous capture throughout the day, with AM/PM mood-equals bookends framing the entry.

## When to use this

- User asks to start, open, or write in today's journal.
- User asks to "add to the daily log" or similar.
- User asks how to set up daily logging in a fresh vault.

## The convention

Four signifiers — use the literal Unicode glyphs at the start of each entry line:

- `–` (en dash, U+2013) note — observations, facts, things to remember
- `•` (bullet, U+2022) action — tasks, things to do
- `○` (white circle, U+25CB) event — meetings, calls, things that happened or will happen
- `=` mood — how you felt; the `=` shape is a prompt to think causally ("our feeling is the result of something")

Don't substitute Markdown list markers (`-`, `*`) for the BuJo glyphs — they render as a uniform bullet list and collapse the visual distinction the symbols are supposed to carry.

### Chaining via indentation

Indent child bullets under a parent event to give the event context. This is Carroll-attested as the structural chaining mechanism:

```
○ Met with Alice about the migration plan
  = Anxious about the timeline
  – Three-week ramp is tighter than I expected
  • Draft pushback email by Thursday
```

### Bookend convention

Each entry opens with a `=` mood line as morning intention and closes with a `=` mood line as evening reflection. Both are written as ordinary Rapid Log entries — they sit at the top and bottom of the same continuous capture stream, not as separate sections.

### Migration

Open `•` actions that don't get done today get rewritten by hand into a future day's entry. Manual; the friction is intentional — re-writing forces a decision about whether the task is still worth doing.

## Default flow

Run these steps in order — don't stop early:

1. **Identify the journal directory.** The default path is `notes/journal/daily/`. If that path doesn't exist, check for a `journal/daily/` or `journal/` directory at the project root. If none exist, ask the user where daily entries should land before creating anything.

2. **Compute today's date** as `YYYY-MM-DD` (use the local date the user is working in — check `date +%F` if unsure).

3. **Check whether today's entry already exists.** If `<journal-dir>/<today>.md` exists, surface its path and stop — do not overwrite. The user may want to append to it manually.

4. **Create today's entry from `template.md`** (shipped alongside this `SKILL.md`). Resolve the skill directory from `CLAUDE_PLUGIN_ROOT` when set; otherwise use the absolute path to this skill's directory. Substitute all three `YYYY-MM-DD` placeholders (the `# YYYY-MM-DD` title and the `created:` / `updated:` frontmatter values) with today's actual date. **Preserve the literal Unicode glyphs** (`–`, `•`, `○`, `=`) in the body — do not substitute ASCII equivalents.

5. **Offer the daily-cadence README on first run.** If `<journal-dir>/README.md` doesn't exist yet, offer to install `vault-readme.md` (shipped alongside this `SKILL.md`) at that path. The README documents the signifiers and conventions for the human reader of the vault. Phrase the offer as a one-word yes/no:

   > "No README at `<journal-dir>/README.md` yet. Install the daily-log conventions README there now?"

   Skip the offer if the README already exists.

6. **Report the path** of today's entry so the user can open it.

## Coaching mode (opt-in)

The default flow is silent capture — create the entry and get out of the way. When the user explicitly asks for help with one of the bookends (phrases like "set my intention," "morning prompt," "reflect on today," "wrap up the day," "close out today"), enter the corresponding sub-flow. **Do not invoke a coach sub-flow on a plain request to open today's journal** — coaching is opt-in, not opportunistic.

### AM intention sub-flow

1. Run the default flow first to ensure today's entry exists.
2. Read the entry. If the **first** `= ` line already has content after the space, the AM bookend is already written — surface what's there and stop. Don't overwrite without explicit user permission.
3. Pick the day-of-week prompt from the AM list in `prompts.md` (Monday → entry 1, Tuesday → 2, …, Sunday → 7). Use the user's local day-of-week.
4. Ask the user the prompt verbatim, in chat. Wait for their answer.
5. Write the answer onto the first `= ` line: preserve the `=` and the single space, then the answer. Do not append punctuation that wasn't in the user's reply.
6. Update the `updated:` frontmatter field to today's date if it isn't already.
7. Report the path and the line that was written.

### PM reflection sub-flow

1. Locate today's entry. If it doesn't exist, ask whether to create one — the user may have skipped capture today, in which case the body-aware step has nothing to read.
2. Read the entry. If the **last** `= ` line already has content after the space, the PM bookend is already written — surface what's there and stop. Don't overwrite without explicit user permission.
3. Read the body — the captures between the bookends. Identify the day's events (`○`), open vs. closed actions (`•`), notable moods (`=`), and any recurring themes.
4. **Generate a body-aware reflection question** grounded in what's actually there (see "Body-aware question principles" below). If the body is empty or too sparse to anchor a question (typical thresholds: fewer than 2 captures, or all captures of the same type with no events), fall back to the day-of-week PM prompt from `prompts.md`.
5. Ask the user the question. Wait for their answer.
6. Write the answer onto the last `= ` line.
7. Update the `updated:` frontmatter field to today's date.
8. Report the path and the line that was written.

### Body-aware question principles (PM)

The AI value-add over a paper journal is reading what actually happened today and asking a question only that day's content makes possible. Some shapes that work:

- **Intention vs. outcome.** The AM `=` said one thing; what happened with it?
- **Unclosed loops.** Open `•` actions still unchecked at end of day — what's the carry-forward decision?
- **Mood arc.** `=` lines through the day shifted from X to Y — what triggered the shift?
- **Event ripples.** A `○` event followed by indented `=` / `–` / `•` children — did its impact resolve, or is it still live?
- **Themes.** Several captures circling the same subject — is there a pattern worth naming?

Pick one. Keep the question short — one or two sentences. Don't stack multiple questions; the goal is reflection, not interrogation. If the body is too sparse to anchor a question, use the day-of-week static fallback rather than fabricating one from nothing.

### Bookend-line heuristic

The skill assumes the template's structure: the **first** `= ` line in the entry is the AM bookend, the **last** is the PM bookend. If the user has hand-edited the entry such that this no longer holds (e.g., deleted the placeholder bookend, or wrote a `=` mood capture before the AM bookend was filled), the heuristic may misfire. In that case, ask before writing rather than guessing.

## Caveats

- **Preserve literal glyphs.** The template uses `–` (en dash), `•` (bullet), `○` (white circle), `=` (equals). Don't normalize these to ASCII when copying — the visual distinction is the point.
- **Capture layer only.** This skill covers the per-day capture page. Cross-day linking, monthly migrations, weekly review pages, and BuJo's processing layer (Collections, Index) are out of scope.
- **Defer to existing vault conventions.** If the project has its own daily-entry template (e.g., a `system/templates/daily-log.md` or similar), use that instead of the skill's shipped template. The shipped one is the default for fresh vaults, not an override for established ones.
- **Frontmatter is intentionally minimal.** The shipped template has only `created` and `updated` dates so it slots into any vault. If the project's other notes carry richer frontmatter (e.g., `related_concepts`, `source_refs`), extend the entry to match — but don't bake project-specific keys into the shared template.
- **Coaching is opt-in.** A plain "open today's journal" doesn't trigger AM coaching. The user has to ask for the prompt explicitly — the BuJo register is freeform capture, and unrequested prompts subtract from that.
