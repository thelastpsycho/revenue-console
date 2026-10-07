export interface Throttle {
  delaySeconds: number
  batchSize: number
  batchPauseMinutes: number
}

/** Rough seconds to send `count` emails with this throttle (~1 s per send). */
export function estimateSendSeconds(count: number, t: Throttle) {
  if (count <= 0) return 0
  const gaps = count - 1
  const pauses = t.batchSize > 0 ? Math.floor(gaps / t.batchSize) : 0
  return count + (gaps - pauses) * t.delaySeconds + pauses * t.batchPauseMinutes * 60
}

export function formatDuration(seconds: number) {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}
