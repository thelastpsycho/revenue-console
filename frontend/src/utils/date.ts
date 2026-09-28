/** 'YYYY-MM-DD' for the browser's local calendar date.
 *
 * Date.toISOString() is UTC - in a timezone ahead of UTC (e.g. Bali, UTC+8),
 * any time before ~8am local still reports yesterday's date there, silently
 * shifting a "start today" default back a day every morning.
 */
export function todayLocalDateString(): string {
  const d = new Date()
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}
