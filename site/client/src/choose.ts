// A choice made in a React part, for the page's script (table.js) to put in the address and fetch
// the list for: {key: value}, null to drop the key
export const choose = (change: Record<string, string | null>) => document.dispatchEvent(new CustomEvent('choose', { detail: change }));
