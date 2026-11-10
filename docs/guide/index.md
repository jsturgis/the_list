---
title: Docs
description: How The List is built, run and deployed.
---

The List is a weekly SF Bay Area music listing, published at [list.sturgis.me](https://list.sturgis.me/). These
guides are for the people who run it and work on it.

- [Overview](overview.md): what The List does each week, and what it's built with.
- [Architecture](architecture.md): diagrams of the site, the backend and the weekly jobs.
- [Local setup](local-setup.md): run the backend, an ingest and the site on your own machine.
- [Configuration](configuration.md): environment variables, and the Google Drive scripts that publish each edition.
- [How ingestion works](ingestion.md): from the Drive edition to Shows, Bands and Venues in the database.
- [Deployment](deployment.md): the weekly Deploy workflow, the `data` branch, backfills and rollbacks.
- [Weekly Alerts](alerts.md): Saved Filters, the weekly Alert email, and their one-time setup.
- [Project structure](project-structure.md): where things live in the repository.

The guides are Markdown in the repository's
[`docs/guide`](https://github.com/jsturgis/the_list/tree/main/docs/guide) folder. The design system, the domain
language and the architecture decisions are in
[`DESIGN.md`](https://github.com/jsturgis/the_list/blob/main/DESIGN.md),
[`CONTEXT.md`](https://github.com/jsturgis/the_list/blob/main/CONTEXT.md) and
[`docs/adr`](https://github.com/jsturgis/the_list/tree/main/docs/adr).
