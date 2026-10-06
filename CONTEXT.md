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
A named musical act — a group, solo artist, or ensemble. DJs and back-to-back DJ sets are excluded. A Band's genres are MusicBrainz's curated genres, else its top Last.fm tags, else its Discogs genres and styles, else MusicBrainz's free-form tags; the edition's genre is used only when every service has none (the edition is always the last fallback). A Band's members (current and former) come from Discogs. A Band's photo is its Wikimedia Commons photo (found through its MusicBrainz Wikidata link, and shown with its credit, as the licence requires), else its Discogs photo (credited "Photo via Discogs"), else the edition's. Either way it's kept with the data: downloaded at ingest, resized and stored on the `data` branch, and served by the site itself rather than linked from where it came from. A Band's `enriched_at` is when it was last looked up on the services: set at ingest for new Bands, and by the backfill for Bands ingested before the lookups existed.
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

### Alerts

**Saved Filter**:
A named set of Show filters belonging to one person, identified by their email address. Stored as the Shows list's URL query string (e.g. `genre=punk&region=east_bay`), so opening it shows the same Shows the site does. It can pin one Band (`bandId=3`, any of a Show's Acts) or Venue (`venueId=2`) by id: the bell on a Band or Venue page saves exactly that. At most 20 per person.
_Avoid_: Saved search (fine in UI copy, not in code), subscription, watch

**Alert**:
The weekly email a person gets after each new edition, listing the Upcoming Shows that match each of their Saved Filters. People can turn Alerts off without deleting their Saved Filters.
_Avoid_: Notification, digest, newsletter
