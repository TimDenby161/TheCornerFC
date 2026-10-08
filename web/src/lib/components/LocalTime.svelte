<script lang="ts">
	import { page } from '$app/state';

	// A kick-off, in the visitor's own time. The server writes it in the time zone it has for them
	// (from the cookie the page sets; UK time on a first visit), and the page puts the browser's
	// own in its place as soon as it is running.
	// show: "day" (Sat 10 Oct), "time" (12:30), "short" (10 Oct)
	let { iso, show }: { iso: string; show: 'day' | 'time' | 'short' } = $props();
	const FORMATS = {
		day: { weekday: 'short', day: 'numeric', month: 'short' },
		time: { hour: 'numeric', minute: '2-digit' },
		short: { day: 'numeric', month: 'short' }
	} as const;
	let local = $state(false);
	$effect(() => { local = true; });
	const there = $derived(local ? {} : { timeZone: (page.data.tz as string) || 'Europe/London' });
	const text = $derived(show === 'time'
		? new Date(iso).toLocaleTimeString(local ? undefined : 'en-GB', { ...FORMATS.time, ...there })
		: new Date(iso).toLocaleDateString(local ? undefined : 'en-GB', { ...FORMATS[show], ...there }));
</script>

<time datetime={iso}>{text}</time>
