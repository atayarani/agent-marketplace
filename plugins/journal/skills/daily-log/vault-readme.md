# Daily journal

Per-day capture pages, one file per day at `YYYY-MM-DD.md`, written into throughout the day as things happen. The shape follows the BuJo Rapid Logging conventions from Ryder Carroll's *The Bullet Journal Method* — symbol-only structure, no section headers, freeform capture from top to bottom.

Use the `daily-log` skill (or invoke it via the slash form your client supports) to create today's entry from the template. The skill defaults to silent capture; ask it explicitly ("morning reflection," "reflect on today," "wrap up the day," "close out today") to walk through Carroll's daily reflection ritual.

## Signifiers

- `–` note — observations, facts, things to remember
- `•` action — tasks, things to do
- `○` event — meetings, calls, things that happened or will happen
- `=` mood — how you felt; the `=` shape is a prompt to think causally ("our feeling is the result of something")

Use the literal Unicode glyphs, not Markdown list markers — `-` and `*` get rendered as a uniform bullet list, which collapses the visual distinction the symbols are supposed to carry. Carroll's signifiers are **content-typed**: a feeling goes on a `=` line, a task goes on a `•` line, regardless of where in the day it's captured.

## Chaining a mood / note / action to an event

Indent child bullets under a parent event to give it context. This is the structural chaining mechanism, per Carroll's transcript:

```
○ Met with Alice about the migration plan
  = Anxious about the timeline
  – Three-week ramp is tighter than I expected
  • Draft pushback email by Thursday
```

## Daily reflection (Carroll-attested ritual)

Daily reflection in Carroll's method is an **activity**, not a positional entry shape. At the start and end of each day, walk through the daily log and edit it — the *practice* lives in the act of walking through, not in a designated section of the page.

**Evening**: review today's open `•` actions. Mark complete the ones you took. For the rest, decide: migrate to a future day, delegate, or drop. Then look over the whole day and capture anything missing.

**Morning**: check the previous day's log. Pull open `•` actions forward to today if still due. Add any other actions that come to mind for today.

The output of reflection is **ordinary signified Rapid Log entries** — newly-captured `•` actions for today (morning carry-forward), state-marker transformations on the previous entry's `•` actions (evening mark-complete / migrate / drop), and any missed `–` notes or `=` moods captured before bed. No "reflection section" lives in the page; reflection's evidence is the state-changes on the daily log entries themselves.

## Dot-state-marker transformations

Carroll's action dot has multiple states beyond open/closed. Replace the `•` prefix **in place** on the existing line — don't add a new line.

- `•` open action (initial state)
- `✕` completed — *"X marks the spot"*
- `→` migrated forward to a future daily log entry (or backward to a monthly log)
- `»` migrated outside the notebook (to a digital task manager, calendar, etc.)
- `~~• action~~` no longer relevant — markdown strikethrough on the whole line, since pure-Unicode dot-with-line-through isn't a common glyph

## Migration

Migrating an open `•` action means transforming its dot to `→` in the original entry **and** re-writing it as a fresh `•` action in the new day's entry. The friction is intentional — re-writing forces a decision about whether the task is still worth doing.

This convention covers the **capture layer** only. Cross-day linking, monthly migrations, weekly review pages, and BuJo's broader processing layer (Collections, Index, future log) aren't covered by this skill.

## Chapter-level intentions (separate, optional)

If a longer-horizon intention shape is wanted, the Carroll-attested home for it is **chapter-level intentions on a labeled page at the start of a new notebook** — format is *Who + What + Why* prose, 1-5 intentions per chapter, on its own indexed page. Distinct from daily reflection; they don't share an artifact.
