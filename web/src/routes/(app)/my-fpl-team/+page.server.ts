import { TAB_INFO } from '#lib/tabInfo.ts';

// The page is the site owner's, and its data is never written here: the owner's browser asks for
// it (/fantasy/data), and the database answers nobody else.
export const load = () => ({ tabHead: { title: 'My FPL team', ...TAB_INFO.myteam } });
