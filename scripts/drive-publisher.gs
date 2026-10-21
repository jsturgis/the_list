/**
 * The List: Drive publisher (Google Apps Script).
 *
 * Moves each week's exports out of the Drive root and keeps a public pointer to the newest
 * formatted edition, so the ingest can download it without Google credentials.
 *
 *   "Bay Area & Santa Cruz Concert Events - <date>.json"  -> PUBLIC folder (anyone with the link)
 *   "San Francisco Area Music List for <date>.enriched.json" -> PUBLIC folder
 *   "... (Raw Email).json"                                -> PRIVATE folder (contains the recipient address)
 *   PUBLIC folder / latest.json                           -> {"latest": {id, name, edition_date, updated},
 *                                                            "enriched": {id, name} of the same edition, or null}
 *   Newest List email from Gmail, footer stripped         -> PUBLIC folder as .txt (see gmail-exporter.gs)
 *
 * A formatted file that still contains personal data (EmailOctopus links, "unsubscribe", a Gmail
 * address) is moved to the PRIVATE folder instead of being published. The enriched export ends with the
 * email footer as an entry with no artists; that entry is dropped first, and the rest is checked for
 * tracking links, "unsubscribe" and this account's address (a band's Gmail address inside a public image
 * URL isn't personal data). A re-generated edition with the
 * same name replaces the published one (the old copy goes to the trash).
 *
 * Setup: paste into a new project at https://script.google.com, run `publish` once (grant Drive access),
 * copy the logged latest.json file id into DRIVE_LATEST_FILE_ID, then run `installTrigger`.
 *
 * When a publish points latest.json at a new (or re-generated) edition, it also dispatches the Deploy
 * workflow on `main` (with ingestion on) so the week's ingest runs right away instead of waiting for
 * GitHub's scheduled fallback. That needs a GitHub token: create a fine-grained personal access token
 * limited to this repository, with Actions read and write, and set it as the GITHUB_TOKEN script
 * property (Project Settings -> Script properties). Without it, publishing still works; the dispatch is
 * just skipped and logged.
 */

const PUBLIC_FOLDER = 'The List (public)';
const PRIVATE_FOLDER = 'The List (raw, private)';
const POINTER_NAME = 'latest.json';
const GITHUB_REPO = 'jsturgis/the_list';
const DEPLOY_WORKFLOW_FILE = 'deploy.yml';
const GITHUB_TOKEN_PROPERTY = 'GITHUB_TOKEN';
const FORMATTED_RE = /^Bay Area & Santa Cruz Concert Events - .+\.json$/;
const ENRICHED_RE = /^San Francisco Area Music List for .+\.enriched\.json$/;
const RAW_RE = /\(Raw Email\)\.json$/;
const PERSONAL_DATA_RE = /eocampaign1\.com|unsubscribe|[A-Za-z0-9._%+-]+@gmail\.com/i;
const TRACKING_RE = /eocampaign1\.com|unsubscribe/i;

function publish() {
  try {
    exportListEmail();  // gmail-exporter.gs: newest List email -> PUBLIC folder as .txt
  } catch (e) {
    Logger.log('Email export failed: %s', e);
  }

  const publicFolder = folder_(PUBLIC_FOLDER, true);
  const privateFolder = folder_(PRIVATE_FOLDER, false);

  const files = DriveApp.getRootFolder().getFiles();
  while (files.hasNext()) {
    const file = files.next();
    const name = file.getName();
    if (RAW_RE.test(name)) {
      file.moveTo(privateFolder);
      file.setSharing(DriveApp.Access.PRIVATE, DriveApp.Permission.NONE);
      Logger.log('Kept private (raw email): %s', name);
    } else if (FORMATTED_RE.test(name) || ENRICHED_RE.test(name)) {
      const reason = ENRICHED_RE.test(name) ? scrubEnriched_(file) : formattedReason_(file);
      if (reason) {
        file.moveTo(privateFolder);
        file.setSharing(DriveApp.Access.PRIVATE, DriveApp.Permission.NONE);
        Logger.log('NOT published (%s): %s', reason, name);
        continue;
      }
      trashSameName_(publicFolder, name);  // a re-generated edition replaces the old copy
      file.moveTo(publicFolder);
      file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      Logger.log('Published: %s', name);
    }
  }

  updatePointer_(publicFolder);
}

/** Why a formatted edition can't be published, or null when it can. */
function formattedReason_(file) {
  const match = file.getBlob().getDataAsString().match(PERSONAL_DATA_RE);
  return match ? 'contains personal data: "' + match[0] + '"' : null;
}

/**
 * Drop the enriched export's footer entry (no artists), then say why the rest can't be published, or
 * return null when it can: it must be a JSON list with no tracking links, "unsubscribe" or this
 * account's address.
 */
function scrubEnriched_(file) {
  let events;
  try {
    events = JSON.parse(file.getBlob().getDataAsString());
  } catch (e) {
    return 'not valid JSON: ' + e.message;
  }
  if (!Array.isArray(events)) return 'not a JSON list of events';
  const kept = events.filter(e => e && e.artists);
  const text = JSON.stringify(kept, null, 2);
  const dropped = events.length - kept.length;
  if (dropped) {
    file.setContent(text);
    Logger.log('Dropped %s footer %s from %s', String(dropped), dropped === 1 ? 'entry' : 'entries', file.getName());
  }
  const tracking = text.match(TRACKING_RE);
  if (tracking) return 'contains tracking text: "' + tracking[0] + '"';
  const me = Session.getEffectiveUser().getEmail();
  if (me && text.toLowerCase().includes(me.toLowerCase())) return "contains this account's address";
  return null;
}

/** Move files with this name in `folder` to the trash. */
function trashSameName_(folder, name) {
  const existing = folder.getFilesByName(name);
  while (existing.hasNext()) {
    const old = existing.next();
    old.setTrashed(true);
    Logger.log('Replaced older copy of %s (id %s)', name, old.getId());
  }
}

/**
 * Point latest.json at the formatted edition with the newest edition_date (latest update wins ties),
 * and at the enriched export for the same date, when there is one. Dispatches the Deploy workflow when
 * that changes which edition the pointer names.
 */
function updatePointer_(publicFolder) {
  const existing = publicFolder.getFilesByName(POINTER_NAME);
  const pointerFile = existing.hasNext() ? existing.next() : null;
  const previousEdition = pointerFile && previousEdition_(pointerFile);

  let newest = null;
  const enrichedByDate = {};
  const files = publicFolder.getFiles();
  while (files.hasNext()) {
    const file = files.next();
    if (ENRICHED_RE.test(file.getName())) {
      const date = enrichedDate_(file.getName());
      const known = enrichedByDate[date];
      if (date && (!known || file.getLastUpdated() > known.getLastUpdated())) enrichedByDate[date] = file;
      continue;
    }
    if (!FORMATTED_RE.test(file.getName())) continue;
    let editionDate;
    try {
      editionDate = JSON.parse(file.getBlob().getDataAsString()).edition_date;
    } catch (e) {
      Logger.log('Skipping unreadable JSON: %s', file.getName());
      continue;
    }
    const updated = file.getLastUpdated().getTime();
    if (editionDate && (!newest || editionDate > newest.edition_date ||
                        (editionDate === newest.edition_date && updated > newest.lastUpdated))) {
      newest = {id: file.getId(), name: file.getName(), edition_date: editionDate, lastUpdated: updated};
    }
  }

  const latest = newest && {id: newest.id, name: newest.name, edition_date: newest.edition_date,
                            updated: new Date().toISOString()};
  const enrichedFile = newest && enrichedByDate[newest.edition_date];
  const enriched = enrichedFile ? {id: enrichedFile.getId(), name: enrichedFile.getName()} : null;
  const content = JSON.stringify({latest: latest, enriched: enriched}, null, 2);
  const pointer = pointerFile || publicFolder.createFile(POINTER_NAME, content, 'application/json');
  pointer.setContent(content);  // same file id every week, so DRIVE_LATEST_FILE_ID never changes
  pointer.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  Logger.log('%s (id %s) -> %s (enriched: %s)', POINTER_NAME, pointer.getId(),
             newest ? newest.name : 'no edition yet', enriched ? enriched.name : 'none');

  maybeDispatchDeploy_(previousEdition, newest);
}

/** The {id, edition_date} the pointer file currently names, or null if it has none or can't be read. */
function previousEdition_(pointerFile) {
  try {
    const data = JSON.parse(pointerFile.getBlob().getDataAsString());
    return data.latest ? {id: data.latest.id, edition_date: data.latest.edition_date} : null;
  } catch (e) {
    return null;
  }
}

/**
 * Dispatch the Deploy workflow on `main`, with ingestion on, when the pointer now names a different
 * edition file than before: a new edition, or a re-generated one with the same edition_date but a new
 * file (compare by file id, not edition_date, so a same-date regeneration still dispatches). Never
 * throws: a missing token or a failed dispatch is logged and the publish still stands. The token is read
 * from the GITHUB_TOKEN script property and never appears in the script or the logs.
 */
function maybeDispatchDeploy_(previousEdition, newest) {
  if (!newest || (previousEdition && newest.id === previousEdition.id)) return;
  const newEditionDate = newest.edition_date;

  const token = PropertiesService.getScriptProperties().getProperty(GITHUB_TOKEN_PROPERTY);
  if (!token) {
    Logger.log('New edition %s but skipped the Deploy dispatch: no %s script property', newEditionDate,
               GITHUB_TOKEN_PROPERTY);
    return;
  }

  try {
    const response = UrlFetchApp.fetch(
      'https://api.github.com/repos/' + GITHUB_REPO + '/actions/workflows/' + DEPLOY_WORKFLOW_FILE + '/dispatches',
      {
        method: 'post',
        contentType: 'application/json',
        headers: {Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json'},
        payload: JSON.stringify({ref: 'main', inputs: {skip_ingest: 'false'}}),
        muteHttpExceptions: true,
      }
    );
    const status = response.getResponseCode();
    if (status === 204) {
      Logger.log('Dispatched Deploy workflow for new edition %s', newEditionDate);
    } else {
      Logger.log('Deploy dispatch failed (status %s): %s', String(status), response.getContentText());
    }
  } catch (e) {
    Logger.log('Deploy dispatch failed: %s', e);
  }
}

const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
                'october', 'november', 'december'];

/** "San Francisco Area Music List for Friday, September 25th, 2026.enriched.json" -> "2026-09-25". */
function enrichedDate_(name) {
  const m = name.match(/ for \w+, (\w+) (\d+)\w*, (\d{4})\.enriched\.json$/);
  const month = m && MONTHS.indexOf(m[1].toLowerCase()) + 1;
  if (!month) return null;
  return m[3] + '-' + String(month).padStart(2, '0') + '-' + m[2].padStart(2, '0');
}

function folder_(name, isPublic) {
  const found = DriveApp.getFoldersByName(name);
  const folder = found.hasNext() ? found.next() : DriveApp.createFolder(name);
  folder.setSharing(isPublic ? DriveApp.Access.ANYONE_WITH_LINK : DriveApp.Access.PRIVATE,
                    isPublic ? DriveApp.Permission.VIEW : DriveApp.Permission.NONE);
  return folder;
}

/**
 * Run once: publish daily between 6pm and 7pm (script time zone, Pacific). Steve's email arrives Friday
 * ~5:20pm, so the new edition is published in time to dispatch that Friday's ingest itself; the Saturday
 * cron in .github/workflows/deploy.yml is only a late fallback for a week the dispatch didn't fire.
 */
function installTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'publish')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('publish').timeBased().everyDays(1).atHour(18).create();
}
