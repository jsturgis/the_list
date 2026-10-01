/**
 * The List: Gmail exporter (Google Apps Script).
 *
 * Finds the newest Steve List email in Gmail and saves its plain-text body to the PUBLIC folder:
 *
 *   "San Francisco Area Music List for Friday, September 25th, 2026.txt"  -> PUBLIC folder
 *
 * The subscriber footer (unsubscribe link, EmailOctopus tracking links) is stripped first. If the text
 * still contains personal data (PERSONAL_DATA_RE or this account's address), it goes to the PRIVATE
 * folder instead. Re-exporting the same edition replaces the earlier copy.
 *
 * Setup: add this file to the same Apps Script project as drive-publisher.gs (it reuses PUBLIC_FOLDER,
 * PRIVATE_FOLDER, PERSONAL_DATA_RE, folder_ and trashSameName_). `publish` calls `exportListEmail`
 * first, so the existing daily trigger covers both. Run `exportListEmail` once by hand to grant
 * Gmail access.
 */

const LIST_QUERY = 'from:skoepke@stevelist.com subject:"San Francisco Area Music List" newer_than:14d';
const FOOTER_START_RE = /^You received this email because/m;
const LINKS_HEADER_RE = /^Links:\s*$/m;

function exportListEmail() {
  const threads = GmailApp.search(LIST_QUERY, 0, 10);
  const messages = threads.map(t => t.getMessages()).reduce((all, m) => all.concat(m), []);
  if (!messages.length) {
    Logger.log('No List email found for: %s', LIST_QUERY);
    return;
  }
  const message = messages.reduce((a, b) => (b.getDate() > a.getDate() ? b : a));

  const name = message.getSubject().replace(/[\\/:*?"<>|]/g, '-') + '.txt';
  const text = scrubFooter_(message.getPlainBody());
  const me = Session.getActiveUser().getEmail();
  const personal = PERSONAL_DATA_RE.test(text) || (me && text.toLowerCase().includes(me.toLowerCase()));

  const target = personal ? folder_(PRIVATE_FOLDER, false) : folder_(PUBLIC_FOLDER, true);
  trashSameName_(target, name);  // a re-export replaces the old copy
  const file = target.createFile(name, text, MimeType.PLAIN_TEXT);
  if (personal) {
    file.setSharing(DriveApp.Access.PRIVATE, DriveApp.Permission.NONE);
    Logger.log('NOT published, contains personal data: %s', name);
  } else {
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    Logger.log('Published email: %s (id %s)', name, file.getId());
  }
}

/** Drop the subscriber footer and any footnote links that point at personal or tracking URLs. */
function scrubFooter_(body) {
  let text = body.replace(/\r\n/g, '\n');
  const footer = text.search(FOOTER_START_RE);
  if (footer !== -1) {
    const links = text.slice(footer).search(LINKS_HEADER_RE);
    text = text.slice(0, footer) + (links === -1 ? '' : text.slice(footer + links));
  }
  return text
    .split('\n')
    .filter(line => !(/^\[\d+\]\s/.test(line) && PERSONAL_DATA_RE.test(line)))
    .join('\n')
    .trimEnd() + '\n';
}
