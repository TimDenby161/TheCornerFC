<script lang="ts">
	import type { Snippet } from 'svelte';
	import { shortName } from '#lib/club.ts';
	import { pageHref } from '#lib/menu.ts';
	import { owner } from '#lib/owner.svelte.ts';
	import Crest from './Crest.svelte';
	import PersonChip from './PersonChip.svelte';

	// A player's cell in a fantasy table: initials with his club's chip on the corner; surname
	// (full name on hover, a link where he has a page here), then `meta` (position, price), any
	// doubt over him, and a line below (his match, or his club).
	let { id, name, team, teamName, tag, line, meta }:
		{ id: number; name: string; team: number; teamName: string; tag: { text: string; title: string } | null; line: string; meta: Snippet } = $props();
</script>

<td class="fpl-player"><div class="fpl-who"><span class="fpl-face"><PersonChip {name} />
	<Crest id={team} name={teamName} href={pageHref('club', team)} /></span>
	<div class="fpl-name"><div class="fpl-line"><span class="fpl-nm" title={name}>{#if owner.known.get(id)}<a class="player-link" href={pageHref('player', id)}>{shortName(name)}</a>{:else}{shortName(name)}{/if}</span>{@render meta()}{#if tag}{' '}<span class="bet-tag warn" title={tag.title}>{tag.text}</span>{/if}</div>
	<div class="fpl-match">{line}</div></div></div></td>
