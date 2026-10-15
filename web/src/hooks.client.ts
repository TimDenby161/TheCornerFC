import type { HandleClientError } from '@sveltejs/kit/hooks';

// A page that fails in the browser (while it is drawn or on a move between pages): its cause is
// shown on an Admin page, where only the administrator can be, and logged to the console.
export const handleError: HandleClientError = ({ error, event }) => {
	console.error(event.url.pathname, error);
	const cause = error instanceof Error ? `${error.message}\n${error.stack ?? ''}` : String(error);
	return { message: 'Internal Error', detail: event.url.pathname.startsWith('/admin') ? cause.slice(0, 1200) : undefined };
};
