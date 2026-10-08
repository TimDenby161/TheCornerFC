<script lang="ts">
	import { personInitials } from '#lib/club.ts';

	// A person's chip: initials on the plain chip colour (no photos: they belong to photographers)
	let { name, size = 'player-photo' }: { name: string; size?: string } = $props();
</script>

<span class="{size} person-chip" aria-hidden="true"><b>{personInitials(name)}</b></span>
