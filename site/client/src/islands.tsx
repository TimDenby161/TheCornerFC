import type { FunctionComponent } from 'react';
import { createRoot } from 'react-dom/client';
import { RankChart } from './RankChart.tsx';

// The page parts React takes over, by the name in their data-island. The server drew each one
// already (so the page reads the same before this runs, and to search engines); its props are the
// JSON in its first <script type="application/json">.
// (each island takes its own props, from the page)
const ISLANDS: Record<string, FunctionComponent<any>> = {
	'rank-chart': RankChart
};

for (const el of document.querySelectorAll<HTMLElement>('[data-island]')) {
	const Island = ISLANDS[el.dataset.island ?? ''];
	const data = el.querySelector(':scope > script[type="application/json"]');
	if (!Island || !data) continue;
	const props: Record<string, unknown> = JSON.parse(data.textContent || '{}');
	createRoot(el).render(<Island {...props} />);
}
