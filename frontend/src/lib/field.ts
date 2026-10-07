/**
 * Every text field, select and date or number input (DESIGN.md, section 4): a `field` pill with a `line-strong`
 * border. Add horizontal padding where it's used (`px-3`, or room for an icon). `items-center` centres a
 * customizable select's text (it lays out as flex).
 *
 * The text is 16px (`text-base`), never smaller: iOS Safari zooms the page in on a focused field under 16px.
 * e2e/form-controls.spec.ts checks every field on the site.
 */
export const FIELD = 'h-9 items-center rounded-full border border-line-strong bg-field text-base text-ink placeholder:text-ink-faint'
