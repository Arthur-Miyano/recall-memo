/**
 * Coalescing, serial save queue.
 *
 * `markDirty` replaces any queued snapshot with the newest one. `flush` waits
 * for the complete chain, so navigation can safely wait before switching
 * documents. A failure leaves the newest snapshot pending but deliberately
 * stops; a later edit or explicit flush may retry it once.
 */
export function createSaveCoordinator(save) {
  let pending = null
  let inFlight = null
  let version = 0

  function markDirty(noteId, payload) {
    pending = { noteId, payload, version: ++version }
    return version
  }

  async function drain() {
    let saved = null
    while (pending) {
      const item = pending
      pending = null
      try {
        const result = await save(item.noteId, item.payload)
        saved = { ...item, result }
      } catch (error) {
        // Preserve a newer edit if one arrived while this request was running;
        // otherwise retain the failed snapshot for an explicit later retry.
        if (!pending) pending = item
        return { ok: false, error, saved }
      }
    }
    return { ok: true, saved }
  }

  function flush() {
    if (inFlight) return inFlight
    if (!pending) return Promise.resolve({ ok: true, saved: null })
    inFlight = drain().finally(() => { inFlight = null })
    return inFlight
  }

  return {
    markDirty,
    flush,
    hasPending: () => pending !== null || inFlight !== null,
  }
}
