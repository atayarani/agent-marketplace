# Daily journal

Per-day capture pages, one file per day at `YYYY-MM-DD.md`, written into throughout the day as things happen. The shape follows the BuJo Rapid Logging conventions from Ryder Carroll's *The Bullet Journal Method* — symbol-only structure, no section headers.

Use the `daily-log` skill (or invoke it via the slash form your client supports) to create today's entry from the template. The skill defaults to silent capture; ask it explicitly ("set my intention," "reflect on today," "wrap up the day") to get a one-question coaching prompt for either bookend — a static day-of-week prompt for the morning, a body-aware question generated from today's captures for the evening.

## Signifiers

- `–` note — observations, facts, things to remember
- `•` action — tasks, things to do
- `○` event — meetings, calls, things that happened or will happen
- `=` mood — how you felt; the `=` shape is a prompt to think causally ("our feeling is the result of something")

Use the literal Unicode glyphs, not Markdown list markers — `-` and `*` get rendered as a uniform bullet list, which collapses the visual distinction the symbols are supposed to carry.

## Chaining a mood / note / action to an event

Indent child bullets under a parent event to give it context. This is the structural chaining mechanism, per Carroll's transcript:

```
○ Met with Alice about the migration plan
  = Anxious about the timeline
  – Three-week ramp is tighter than I expected
  • Draft pushback email by Thursday
```

## Bookend convention

Each daily entry opens with a `=` intention bookend (one-line morning intention) and closes with a `=` reflection bookend (one or two lines, end of day). Both are written as ordinary Rapid Log entries — they sit at the top and bottom of the same continuous capture stream, not as separate sections.

## Migration

Open `•` actions that don't get done today get rewritten by hand into a future day's entry. The friction is intentional — re-writing forces a decision about whether the task is still worth doing.

This convention covers the **capture layer** only. Cross-day linking, monthly migrations, and BuJo's processing layer aren't covered by this skill.
