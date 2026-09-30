/**
 * The List: Drive publisher (Google Apps Script).
 *
 * Moves each week's exports out of the Drive root and keeps a public pointer to the newest
 * formatted edition, so the ingest can download it without Google credentials.
 *
 *   "Bay Area & Santa Cruz Concert Events - <date>.json"  -> PUBLIC folder (anyone with the link)
 *   "... (Raw Email).json"                                -> PRIVATE folder (contains the recipient address)
 *   PUBLIC folder / latest.json                           -> {"latest": {id, name, edition_date, updated}}
 *
 * A formatted file that still contains personal data (EmailOctopus links, "unsubscribe", a Gmail
 * address) is moved to the PRIVATE folder instead of being published.
 *
 * Setup: paste into a new project at https://script.google.com, run `publish` once (grant Drive access),
 * copy the logged latest.json file id into DRIVE_LATEST_FILE_ID, then run `installTrigger`.
 */

const PUBLIC_FOLDER = 'The List (public)';
const PRIVATE_FOLDER = 'The List (raw, private)';
const POINTER_NAME = 'latest.json';
const FORMATTED_RE = /^Bay Area & Santa Cruz Concert Events - .+\.json$/;
const RAW_RE = /\(Raw Email\)\.json$/;
const PERSONAL_DATA_RE = /eocampaign1\.com|unsubscribe|[A-Za-z0-9._%+-]+@gmail\.com/i;

function publish() {
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
    } else if (FORMATTED_RE.test(name)) {
      if (PERSONAL_DATA_RE.test(file.getBlob().getDataAsString())) {
        file.moveTo(privateFolder);
        file.setSharing(DriveApp.Access.PRIVATE, DriveApp.Permission.NONE);
        Logger.log('NOT published, contains personal data: %s', name);
        continue;
      }
      file.moveTo(publicFolder);
      file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      Logger.log('Published: %s', name);
    }
  }

  updatePointer_(publicFolder);
}

/** Point latest.json at the formatted edition with the newest edition_date. */
function updatePointer_(publicFolder) {
  let newest = null;
  const files = publicFolder.getFiles();
  while (files.hasNext()) {
    const file = files.next();
    if (!FORMATTED_RE.test(file.getName())) continue;
    let editionDate;
    try {
      editionDate = JSON.parse(file.getBlob().getDataAsString()).edition_date;
    } catch (e) {
      Logger.log('Skipping unreadable JSON: %s', file.getName());
      continue;
    }
    if (editionDate && (!newest || editionDate > newest.edition_date)) {
      newest = {id: file.getId(), name: file.getName(), edition_date: editionDate};
    }
  }

  const content = JSON.stringify({latest: newest && Object.assign(newest, {updated: new Date().toISOString()})}, null, 2);
  const existing = publicFolder.getFilesByName(POINTER_NAME);
  const pointer = existing.hasNext() ? existing.next() : publicFolder.createFile(POINTER_NAME, content, 'application/json');
  pointer.setContent(content);  // same file id every week, so DRIVE_LATEST_FILE_ID never changes
  pointer.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  Logger.log('%s (id %s) -> %s', POINTER_NAME, pointer.getId(), newest ? newest.name : 'no edition yet');
}

function folder_(name, isPublic) {
  const found = DriveApp.getFoldersByName(name);
  const folder = found.hasNext() ? found.next() : DriveApp.createFolder(name);
  folder.setSharing(isPublic ? DriveApp.Access.ANYONE_WITH_LINK : DriveApp.Access.PRIVATE,
                    isPublic ? DriveApp.Permission.VIEW : DriveApp.Permission.NONE);
  return folder;
}

/** Run once: publish daily at about 6am, well before the Friday-evening ingest. */
function installTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'publish')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('publish').timeBased().everyDays(1).atHour(6).create();
}
