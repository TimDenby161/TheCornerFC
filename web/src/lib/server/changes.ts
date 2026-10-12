import { adminDoc } from '#lib/server/admin.ts';
import type { ChangesDoc } from '#lib/changes.ts';

// The administrator's model change record, or null before the export has stored one. Asked afresh
// for every request with the visitor's own token: it is never kept in the Worker, so it can't
// reach anyone the database wouldn't give it to.
export const changesDoc = (fetch: typeof globalThis.fetch, token: string | undefined) => adminDoc<ChangesDoc>(fetch, token, 'model_changes');
