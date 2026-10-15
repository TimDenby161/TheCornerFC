import type { SupabaseClient } from '@supabase/supabase-js';

declare global {
	// the commit this build was made from (vite.config.ts), for /version
	const __COMMIT__: string;
	namespace App {
		// what a failed page says: the cause is added for a signed-in administrator only (hooks.server.ts)
		interface Error {
			message: string;
			detail?: string;
		}
		// the Worker's own settings (wrangler.jsonc): which environment it is set up as
		interface Platform {
			env?: { SITE_ENV?: string };
		}
		interface Locals {
			// the sign-in service, reading and writing this visitor's session cookie
			supabase: SupabaseClient;
			// the signed-in visitor, and the token their requests to the database carry (so it can
			// give a subscriber the paid rows); both undefined when signed out
			user?: { id: string; email: string };
			token?: string;
			// set by the hook on an address under /admin, once the database has said this visitor is an administrator
			admin?: boolean;
		}
	}
}

export {};
