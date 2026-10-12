import { siteEnvironment } from './environments.ts';

// Which copy of the site this build is, production or staging: named by the build, never assumed
// (environments.ts). Everything that differs between the two comes from here.
export const SITE = siteEnvironment(import.meta.env.VITE_SITE_ENV);
export const SITE_ENV = SITE.name;

// Supabase's public key: on its own the database lets it call nothing but the functions granted
// to it (site_doc and the site_* queries).
export const SUPABASE = { url: SITE.url, key: SITE.key };

// Adverts: off. The two spaces kept for them (#ad-top, #ad-rail; sizes and pages in the
// stylesheet: never Home, the two betting pages, the fantasy pages or the text pages) take no room
// until this is true. ?ads=preview in the address draws the spaces as marked boxes. Nothing loads
// an advert yet: the network's script, the consent banner and the security policy's change
// (vite.config.ts) come with the network. A subscriber sees no adverts.
export const ADS = { on: false };

// What a subscription costs (owner, 2026-10-07). The charge itself is the price set in Stripe:
// these are the words on the buttons, and the two must be changed together.
export const PRICES = { monthly: '£4.99 a month', yearly: '£49 a year' };

// The site's own address. The app also answers at its workers.dev preview address; www goes to this.
export const SITE_HOST = SITE.host;
