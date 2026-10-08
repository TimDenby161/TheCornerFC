<script lang="ts">
	import type { Chip, Menu, MenuNode } from '#lib/clubTable.ts';

	// The country / league menu. Each choice is a button of a form that writes it into the
	// address (`name`), so it works before the page's script has loaded; `keep` is the page's
	// other choices, carried along. Wide screens: a side menu, a group opening after a short
	// hover. Narrower: the same menu behind a button naming the selection.
	let { menu, name = 'c', action, keep = {}, id }: { menu: Menu; name?: string; action: string; keep?: Record<string, string>; id: string } = $props();

	let open = $state(false);
	let hovered = $state<string[]>([]);
	let wrap: HTMLElement;
	let timer: ReturnType<typeof setTimeout> | undefined;

	function enter(value: string) {
		if (!matchMedia('(hover: hover)').matches) return;
		clearTimeout(timer);
		timer = setTimeout(() => { if (!hovered.includes(value)) hovered = [...hovered, value]; }, 150);
	}
	function leave() {
		clearTimeout(timer);
		timer = setTimeout(() => (hovered = []), 300);
	}
	// picking a group opens it and the menu stays open to go further in; anything else closes it
	const picked = (chip: Chip) => { if (!chip.group) open = false; };
</script>

<svelte:document onclick={(e) => { if (open && !wrap.contains(e.target as Node)) open = false; }} />

{#snippet chipButton(chip: Chip)}
	<button type="submit" {name} value={chip.value} class="filter-chip" class:cchip={chip.group} class:has-active={chip.hasActive} class:none={chip.count === 0}
		title={chip.title} aria-pressed={chip.pressed} onclick={() => picked(chip)}>
		{#if chip.group}<span class="caret" aria-hidden="true">▾</span>{/if}<span class="flabel">{chip.label}</span>{#if chip.count != null}<span class="cnt">{chip.count}</span>{/if}
	</button>
{/snippet}

{#snippet node(n: MenuNode)}
	{#if n.sep}
		<div class="sep"></div>
	{:else if n.children}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="cgroup" class:region={n.region} class:open={n.open} class:hover-open={hovered.includes(n.chip.value)} onmouseenter={() => enter(n.chip.value)}>
			{@render chipButton(n.chip)}
			<div class="league-list"><div class="ll-inner">{#each n.children as child, i (i)}{@render node(child)}{/each}</div></div>
		</div>
	{:else}
		{@render chipButton(n.chip)}
	{/if}
{/snippet}

<div class="filters-wrap side-filters" class:menu-open={open} {id} bind:this={wrap}>
	<form class="contents" method="get" {action} data-sveltekit-reset="false">
		{#each Object.entries(keep) as [k, v] (k)}<input type="hidden" name={k} value={v} />{/each}
		<button type="button" class="menu-trigger" aria-expanded={open} onclick={() => (open = !open)}>
			<span class="mt-name">{menu.name}</span>{#if menu.count != null}<span class="cnt">{menu.count}</span>{/if}<span class="caret" aria-hidden="true">▾</span>
		</button>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="cgroups" onmouseleave={leave}>
			{#each menu.nodes as n, i (i)}{@render node(n)}{/each}
		</div>
	</form>
</div>
