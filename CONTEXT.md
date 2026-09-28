# The List

A weekly SF Bay Area music discovery app that ingests Steve List's curated email, enriches it, and presents upcoming shows in a browsable, searchable format.

## Language

### Core entities

**Show**:
A single booking at a Venue on a specific date — one or more Acts performing together. The primary unit of discovery.
_Avoid_: Event, listing, gig

**Act**:
A Band's appearance within a Show. The first Act is the headliner; subsequent Acts are support.
_Avoid_: Performer, artist (use Band or Act depending on context)

**Band**:
A named musical act — a group, solo artist, or ensemble. DJs and back-to-back DJ sets are excluded.
_Avoid_: Artist, performer, act (when referring to the entity itself rather than its role in a Show)

**Venue**:
A named physical location where Shows occur, belonging to a City and Region.
_Avoid_: Location, space, club

**Region**:
A geographic grouping of cities used for filtering: SF · East Bay · North Bay · South Bay · Santa Cruz.
_Avoid_: Area, zone, neighborhood

### Show status

**Upcoming**:
A Show whose date is in the future and has not been cancelled or postponed.

**Past**:
A Show whose date has passed. Past Shows are retained for 3 months, then hard-deleted.

**Cancelled**:
A Show that will not take place, as indicated by a `CANCELLED:` prefix in the source email.

**Postponed**:
A Show that has been delayed to an unconfirmed date, as indicated by a `POSTPONED:` prefix in the source email.

### Show flags

**Steve's Pick** (`*`):
A Show personally recommended by Steve List. Surfaced prominently in the UI.
_Avoid_: Featured, staff pick, recommended

**Will Sell Out** (`$`):
A Show flagged by Steve as likely to sell out. Prioritised for ticket link enrichment.

**Pit Warning** (`@`):
A Show with a standing/mosh pit. Useful for attendees who want to avoid pits.

**Drink Tickets** (`^`):
A Show where under-21 attendees must purchase drink tickets on entry.
_Avoid_: Under-21 surcharge

**No Re-entry** (`#`):
A Show with a no ins/outs policy — attendees cannot leave and re-enter.
