---
name: weekly-log
description: >-
  Open this week's BuJo-style weekly log entry. Creates `notes/journal/weekly/YYYY-Www.md` (ISO 8601 week-date format, e.g., 2026-W20) from a Rapid-Logging template using the same four-signifier vocabulary as daily-log (`–` note / `•` action / `○` event / `=` mood) and dot-state-marker transformations (`✕` complete / `→` migrated / `»` exported / `~~•~~` dropped). Default mode is silent capture. Opt-in coaching (triggered by phrases like "weekly reflection," "plan this week," "weekly review") walks Carroll's weekly ritual — reflect on the week gone by (state-mark open actions, capture themes) then build the week's action plan (list actions for the next 7 days, then **time-block onto the calendar** per Carroll's pro-tip). Designed to stack with `daily-log` and `monthly-log`: same template shape, same signifiers; the daily AM ritual reads the current week's action plan as zoom-out context.
---

You're helping the user with the **weekly cadence** of a BuJo-style journal. Same Rapid Logging conventions as daily-log (see that skill's SKILL.md or the vault README for the four-signifier vocabulary + dot-state-marker transformations); this skill adds the weekly ritual shape Carroll names in *How to Bullet Journal: Daily vs. Weekly vs. Monthly*.

## When to use this

- User asks to start, open, or write in this week's weekly log.
- User asks for a weekly reflection ("weekly reflection," "review the week").
- User asks to plan this week ("plan this week," "weekly action plan").
- User asks how to set up weekly logging in a fresh vault.

## The convention

Weekly entries use the same four-signifier vocabulary as daily entries (`–` note / `•` action / `○` event / `=` mood) and the same dot-state-marker transformations (`✕` / `→` / `»` / `~~•~~`). See `daily-log/SKILL.md` for the signifier reference. The weekly cadence's distinctive structural shape is **list-and-time-block**, described below.

### Carroll's weekly action plan recipe

From *How to Bullet Journal: Daily vs. Weekly vs. Monthly*: *"For the weekly plan, it's just like the month. We simply list actions we want to take for this week. Again, we're not listing everything that has to be done, only that which we want to get done in the next seven days. Pro tip — once your weekly action plan is in place, time-block those actions on your calendar. After all, for many of us, our calendar determines our day-to-day."*

The recipe is:

1. **List**: brainstorm actions you want to take this week as `•` action lines. Carroll's framing: "what we want to get done in the next seven days" — not an exhaustive todo, a deliberate choice of focus.
2. **Time-block onto calendar**: Carroll's distinctive pro-tip — once the list exists, schedule each `•` onto a specific block on your external calendar (Google Calendar, iCal, Notion calendar, etc.). The weekly action plan in the BuJo entry is the canonical list; the calendar is the operational layer.

Carroll doesn't impose a numeric cap on weekly actions (unlike the monthly 4-priority cap) — the constraint is "next seven days" rather than a count.

### "Goldilocks zone" for variable schedules

Carroll explicitly frames weekly as the highest-leverage cadence for many people: *"For many, this is the Goldilocks zone of planning. It's a great planning cadence for those with schedules or workloads that are constantly changing — when each week is a whole new adventure. Sitting down every seven days can be a great way to regroup and reset and make sure that you're focusing on the right things. It's also a great cadence for those whose schedules are pretty straightforward — if not much changes for you from week to week, this is a great way for you to make sure that you're not living on autopilot."*

If a user is debating whether to add weekly, the Goldilocks framing is the case for it.

### Cross-cadence stacking

The weekly entry is the *midpoint anchor* between monthly (zoom-out: this month's 4 priorities) and daily (zoom-in: today's actions). Each week's action plan should ideally advance one or more of the month's priorities. The daily AM ritual reads the current week's action plan as zoom-out context.

### ISO week-date format

Weekly entries use ISO 8601 week-date format: `YYYY-Www` (e.g., `2026-W20.md`). The "W" is a literal capital letter; weeks are zero-padded to two digits.

ISO weeks start Monday and the first week of the year contains the first Thursday. This convention is unambiguous and sortable (so weekly entries sort chronologically when listed alphabetically). Compute the ISO week via `date +%G-W%V` on most Unix-like systems.

## Default flow

Run these steps in order — don't stop early:

1. **Identify the journal directory.** The default path is `notes/journal/weekly/`. If that path doesn't exist, check for a `journal/weekly/` or `journal/` directory at the project root. If none exist, ask the user where weekly entries should land before creating anything.

2. **Compute this week** as `YYYY-Www` (ISO 8601 week-date format; e.g., `2026-W20`). Use `date +%G-W%V` if unsure.

3. **Check whether this week's entry already exists.** If `<journal-dir>/<YYYY-Www>.md` exists, surface its path and stop — do not overwrite. The user may want to append to it manually.

4. **Create this week's entry from `template.md`** (shipped alongside this `SKILL.md`). Resolve the skill directory from `CLAUDE_PLUGIN_ROOT` when set; otherwise use the absolute path to this skill's directory. Substitute the `YYYY-Www` title placeholder with this week's ISO week-date, and the `created:` / `updated:` frontmatter values with today's `YYYY-MM-DD`. **Preserve the literal Unicode glyphs** (`–`, `•`, `○`, `=`) in the body.

5. **Offer the weekly-cadence README on first run.** If `<journal-dir>/README.md` doesn't exist yet, offer to install `vault-readme.md` (shipped alongside this `SKILL.md`) at that path. Phrase the offer as a one-word yes/no.

6. **Report the path** of this week's entry so the user can open it.

## Coaching mode (opt-in)

The default flow is silent capture. When the user explicitly asks for help with the weekly ritual (phrases like "weekly reflection," "review the week," "plan this week," "weekly action plan"), enter the corresponding sub-flow.

Carroll's weekly ritual is two halves: **reflect on the week gone by** + **plan the week ahead**. Same shape as the monthly ritual.

### Weekly reflection sub-flow

1. Locate the **previous** weekly-log entry (the most recent `YYYY-Www.md` before this week). If none exists, skip to the planning sub-flow.
2. **Read the previous weekly entry's open `•` actions** (those not yet state-marked). Walk each:
   - **Complete**: transform the prefix from `•` to `✕` on the existing line.
   - **Migrate to this week**: transform to `→` AND re-write as a fresh `•` action in this week's entry.
   - **Drop**: transform to `~~• action~~`.
3. Ask: *"Anything else from last week worth capturing — themes, observations, mood shifts?"* Capture as appropriate signified entries (`–` notes, `=` moods) in the previous week's entry.

### Weekly planning sub-flow

1. Run the default flow first to ensure this week's entry exists.
2. **(Optional) Read this month's monthly-log entry** for the 4 priorities. Surface them as zoom-out context: *"This month's priorities are 1. X, 2. Y, 3. Z, 4. W. The week's actions should advance one or more of these — what do you want to focus on this week?"*
3. **List actions for the next 7 days**. Capture each as `• <action>` in this week's entry. Keep going until the user signals done.
4. **Apply Carroll's time-block pro-tip**. Ask: *"Want to time-block these onto your calendar now? I can list them in order so you can drag them onto specific slots."* If the user says yes, list the actions back in a numbered list ready to paste/schedule. The time-blocking itself happens in the user's external calendar — the BuJo entry is the canonical list, not the schedule.
5. Update `updated:` frontmatter.
6. Report what was committed as the week's action plan.

### Empty-state fallback

If the previous weekly entry has no open `•` actions to walk (empty or first-week-in-vault), skip the reflection sub-flow and go straight to the planning sub-flow.

## Caveats

- **Same signifiers + state-markers as daily-log**. The four-signifier vocabulary (`–` / `•` / `○` / `=`) and dot-state-marker transformations (`✕` / `→` / `»` / `~~•~~`) are shared across all three cadences. See `daily-log/SKILL.md` or the vault README for the full reference.
- **No numeric cap.** Unlike monthly's 4-priority cap, weekly has no Carroll-imposed numeric ceiling. The constraint is "next seven days" — a time-bound, not a count-bound.
- **Time-blocking happens in an external calendar.** The BuJo weekly entry holds the canonical action list; the calendar holds the schedule. The skill prompts the user to time-block but doesn't write to the calendar directly — that's an out-of-band step in the user's calendar tool.
- **ISO 8601 week-date format.** Weeks are `YYYY-Www` (e.g., `2026-W20`); the `W` is literal, weeks zero-padded. Compute via `date +%G-W%V` for accuracy across year boundaries (ISO weeks that span December/January attribute to the year containing the week's Thursday — `%G` handles this, `%Y` doesn't).
- **Reflection is content-editing.** Same as daily and monthly: reflection state-marks the previous entry's open actions and captures any missed observations. No "reflection section" in the entry.
- **Designed to stack.** Carroll's *"our planning rituals are designed to stack to support each other"* — daily + weekly + monthly share signifier vocabulary, state-marker transformations, and reflection-as-activity shape. See `daily-log/SKILL.md` for the canonical convention reference.
- **Defer to existing vault conventions.** If the project has its own weekly-entry template (e.g., `system/templates/weekly-log.md`), use that instead.
