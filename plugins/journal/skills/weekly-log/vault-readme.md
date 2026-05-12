# Weekly journal

Per-week capture pages, one file per ISO week at `YYYY-Www.md` (e.g., `2026-W20.md`), written into across the week as actions get checked off and reflection notes accumulate. Shape follows the BuJo Rapid Logging conventions from Ryder Carroll's *How to Bullet Journal: Daily vs. Weekly vs. Monthly*. Same signifier vocabulary as the daily and monthly cadences — see [[notes/journal/daily/README|the daily journal README]] for the canonical convention reference.

## The weekly action plan

Carroll's weekly-cadence shape:

1. **List**: actions you want to take in the next 7 days as `•` action lines. *"Not listing everything that has to be done, only that which we want to get done in the next seven days."*
2. **Time-block onto calendar**: Carroll's distinctive pro-tip — once the list exists, schedule each `•` onto a specific block in your external calendar. The BuJo entry is the canonical list; the calendar is the operational layer.

No Carroll-imposed numeric cap on weekly actions (unlike monthly's 4-priority cap). The constraint is "next seven days" — time-bound, not count-bound.

## Weekly reflection (Carroll-attested ritual)

At the start of each week, walk the **previous** weekly entry's open `•` actions and state-mark each:

- `✕` — completed
- `→` — migrated to this week (re-write as a fresh `•` in this week's entry)
- `»` — exported (moved to a digital task manager, calendar, etc.)
- `~~• action~~` — dropped, no longer relevant

Then capture any reflection notes about the week gone by (themes, mood shifts, what worked, what didn't) as ordinary signified entries (`–` notes, `=` moods) on the previous week's entry.

## "Goldilocks zone" for variable schedules

Carroll frames weekly as the highest-leverage cadence for many: *"the Goldilocks zone of planning... a great cadence for those with schedules or workloads that are constantly changing — when each week is a whole new adventure"* AND *"a great way for those whose schedules are pretty straightforward to make sure that you're not living on autopilot."*

If you're choosing between cadences, weekly is the safest default.

## Stacking with monthly and daily

The weekly entry is the **midpoint anchor** between monthly (zoom-out: this month's 4 priorities) and daily (zoom-in: today's actions):

- Each week's action plan should ideally advance one or more of [[notes/journal/monthly|this month's]] 4 priorities.
- This week's action plan surfaces in the [[notes/journal/daily|daily]] AM ritual (via the `daily-log` skill's cross-cadence read).

## ISO 8601 week-date format

Files are named `YYYY-Www.md` (capital `W`, zero-padded two-digit week, e.g., `2026-W20.md`). ISO weeks start Monday; the first week of the year contains the first Thursday. Compute with `date +%G-W%V` (`%G` is the ISO week-numbering year, which handles weeks that span December/January correctly).
