import type { HandleClientError } from '@sveltejs/kit/hooks';

// A page that fails in the browser: the fault goes to the console, never onto the page. The
// visitor sees the error page's plain words (lib/components/ErrorPage.svelte).
export const handleError: HandleClientError = ({ error, event }) => {
	console.error(event.url.pathname, error);
	return { message: 'Internal Error' };
};
