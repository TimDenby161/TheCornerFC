<script lang="ts">
	// A signed change: green with a plus when up, red when down, a plain 0, nothing when unknown.
	let { value }: { value: number | null } = $props();
</script>

{#if value == null}{:else if value > 0}<span class="form-up">+{value}</span>{:else if value < 0}<span class="form-down">{value}</span>{:else}0{/if}
