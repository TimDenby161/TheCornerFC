<script lang="ts">
	// A kick-off, in the visitor's own time. The server can't know where they are, so it writes
	// UK time, and the page puts the visitor's own in its place as soon as it is running.
	// show: "day" (Sat 10 Oct), "time" (12:30), "short" (10 Oct)
	let { iso, show }: { iso: string; show: 'day' | 'time' | 'short' } = $props();
	const FORMATS = {
		day: { weekday: 'short', day: 'numeric', month: 'short' },
		time: { hour: 'numeric', minute: '2-digit' },
		short: { day: 'numeric', month: 'short' }
	} as const;
	let local = $state(false);
	$effect(() => { local = true; });
	const text = $derived(show === 'time'
		? new Date(iso).toLocaleTimeString(local ? undefined : 'en-GB', { ...FORMATS.time, ...(local ? {} : { timeZone: 'Europe/London' }) })
		: new Date(iso).toLocaleDateString(local ? undefined : 'en-GB', { ...FORMATS[show], ...(local ? {} : { timeZone: 'Europe/London' }) }));
</script>

<time datetime={iso}>{text}</time>
