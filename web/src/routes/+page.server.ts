import { redirect } from '@sveltejs/kit';

// Home is not rebuilt yet: the first page here is the Clubs table.
export const load = () => redirect(307, '/clubs');
