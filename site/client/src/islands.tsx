import type { FunctionComponent } from 'react';
import { createRoot } from 'react-dom/client';
import { DualRange, PlayerRanges } from './DualRange.tsx';
import { matchCards } from './MatchCards.tsx';
import { RankChart } from './RankChart.tsx';
import { WhoPicker } from './WhoPicker.tsx';

// The page parts React takes over, by the name in their data-island. The server drew each one
// already (so the page reads the same before this runs, and to search engines); its props are the
// JSON in its first <script type="application/json">. When the page swaps in the server's answer
// to a new choice (table.js), each part is handed its new props in an "island-props" event.
// (each island takes its own props, from the page)
const ISLANDS: Record<string, FunctionComponent<any>> = {
	'rank-chart': RankChart,
	'player-ranges': PlayerRanges,
	'player-age': DualRange,
	'who-picker': WhoPicker
};

for (const el of document.querySelectorAll<HTMLElement>('[data-island]')) {
	const Island = ISLANDS[el.dataset.island ?? ''];
	const data = el.querySelector(':scope > script[type="application/json"]');
	if (!Island || !data) continue;
	const root = createRoot(el);
	const draw = (props: Record<string, unknown>) => root.render(<Island {...props} />);
	draw(JSON.parse(data.textContent || '{}'));
	el.addEventListener('island-props', (e) => draw((e as CustomEvent<Record<string, unknown>>).detail));
}

// Match cards: their line-ups, model detail and squads, wherever a page has them
matchCards();
