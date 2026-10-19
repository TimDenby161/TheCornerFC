// An instant in the visitor's own time (LocalTime.svelte), as the server writes one: in the zone
// it has for them (the page reloads when the browser's own differs), British style.
// show: "day" (Sat 10 Oct), "time" (12:30), "short" (10 Oct)
const FORMATS = {
	day: { weekday: 'short', day: 'numeric', month: 'short' },
	time: { hour: 'numeric', minute: '2-digit' },
	short: { day: 'numeric', month: 'short' }
} as const;
export function LocalTime({ iso, show }: { iso: string; show: keyof typeof FORMATS }) {
	const timeZone = document.body.dataset.tz || 'Europe/London';
	const at = new Date(iso);
	const text = show === 'time' ? at.toLocaleTimeString('en-GB', { ...FORMATS.time, timeZone }) : at.toLocaleDateString('en-GB', { ...FORMATS[show], timeZone });
	return <time dateTime={iso} data-show={show}>{text}</time>;
}
