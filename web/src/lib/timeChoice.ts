import { TZ_OFF } from './matchday.ts';

// The time zone cookie, written in the browser: the browser's own zone, or TZ_OFF for a visitor
// who chose UK time in the menu (the choice alone is kept then, not where they are).
export const keepZone = (value: string) => {
	document.cookie = `tz=${encodeURIComponent(value)}; path=/; max-age=31536000; samesite=lax${location.protocol === 'https:' ? '; secure' : ''}`;
};
export const browserZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || '';
export const keepUkTime = () => keepZone(TZ_OFF);
