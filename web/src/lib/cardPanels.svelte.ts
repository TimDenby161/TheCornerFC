// Which match card has a panel open (its line-ups or its model detail). One card at a time in a
// list: opening one closes the last.
export const cardPanels = $state<{ id: number | null; lineups: boolean; why: boolean }>({ id: null, lineups: false, why: false });
export function togglePanel(id: number, part: 'lineups' | 'why') {
	if (cardPanels.id !== id) { cardPanels.id = id; cardPanels.lineups = false; cardPanels.why = false; }
	cardPanels[part] = !cardPanels[part];
}
