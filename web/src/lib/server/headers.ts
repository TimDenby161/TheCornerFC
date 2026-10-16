// The security headers every page and redirect carries, beside the security policy that
// vite.config.ts sets (audit finding S19, 2026-10-16).
//   Strict-Transport-Security   browsers use https for a year, here and on every subdomain
//                               (staging, www), without trying http first
//   X-Content-Type-Options      a file is only ever what its type says
//   Referrer-Policy             other sites see only thecornerfc.com, never the page (as the
//                               privacy page says of flagcdn.com)
//   Permissions-Policy          no page here may ask for the camera, microphone, location,
//                               payment handler or USB, or join ad-topic tracking
export const SECURITY_HEADERS: Readonly<Record<string, string>> = {
	'strict-transport-security': 'max-age=31536000; includeSubDomains',
	'x-content-type-options': 'nosniff',
	'referrer-policy': 'strict-origin-when-cross-origin',
	'permissions-policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()'
};

// Adds them to a response, replacing any already there. A redirect's headers can't be changed,
// so it comes back as a new response with the same status and address.
export function secured(response: Response): Response {
	let out = response;
	try {
		for (const [k, v] of Object.entries(SECURITY_HEADERS)) out.headers.set(k, v);
	} catch {
		out = new Response(response.body, { status: response.status, statusText: response.statusText, headers: response.headers });
		for (const [k, v] of Object.entries(SECURITY_HEADERS)) out.headers.set(k, v);
	}
	return out;
}
