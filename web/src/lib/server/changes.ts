import { adminDoc } from '#lib/server/admin.ts';
import type { ChangesDoc, LiveDoc } from '#lib/changes.ts';

// The administrator's model change record, or null before the export has stored one. Asked afresh
// for every request with the visitor's own token: it is never kept in the Worker, so it can't
// reach anyone the database wouldn't give it to.
export const changesDoc = (fetch: typeof globalThis.fetch, token: string | undefined) => adminDoc<ChangesDoc>(fetch, token, 'model_changes');
// Protocol P15's running record of every runnable change on live matches, or null before the
// Live tracking workflow has stored one. The same rules: the visitor's own token, never kept.
export const liveDoc = (fetch: typeof globalThis.fetch, token: string | undefined) => adminDoc<LiveDoc>(fetch, token, 'live_tracking');
