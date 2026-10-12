import { redirect } from '@sveltejs/kit';

// The Admin area opens on the Model Change Tracker
export function load() {
	redirect(303, '/admin/changes');
}
