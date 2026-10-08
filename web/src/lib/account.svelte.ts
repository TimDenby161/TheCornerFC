// The account box, which the menu's button opens. Kept here so that anything on a page can open
// it too: a "What subscribers get" link opens it on that view.
export const accountBox = $state<{ open: boolean; view: string | null }>({ open: false, view: null });
export const openAccount = (view: string | null = null) => { accountBox.view = view; accountBox.open = true; };
