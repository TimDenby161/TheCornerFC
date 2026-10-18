import info from './tabInfo.json';

// Each section's line of introduction and what its figures mean, carried over from the old site's
// app.js. `more`: the part of the methodology page that explains it. The words are in
// tabInfo.json, which the C# site (site/) reads too.
export type TabInfo = { intro: string; more: string; key: [string, string][] };
export const TAB_INFO = info as unknown as Record<string, TabInfo>;
