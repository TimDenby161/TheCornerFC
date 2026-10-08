import type { SupabaseClient } from '@supabase/supabase-js';

declare global {
	namespace App {
		interface Locals {
			// the sign-in service, reading and writing this visitor's session cookie
			supabase: SupabaseClient;
			// the signed-in visitor, and the token their requests to the database carry (so it can
			// give a subscriber the paid rows); both undefined when signed out
			user?: { id: string; email: string };
			token?: string;
		}
	}
}

export {};
