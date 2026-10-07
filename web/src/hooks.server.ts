import type { Handle } from '@sveltejs/kit/hooks';
import { tabFor } from '#lib/menu.ts';

// The stylesheet lays a section out by the name on <body data-tab>, so the server writes it.
export const handle: Handle = ({ event, resolve }) =>
	resolve(event, { transformPageChunk: ({ html }) => html.replace('%tab%', tabFor(event.url.pathname)) });
