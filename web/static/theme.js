// The Light or Dark theme picked in the site menu, applied before the page draws.
// Nothing stored: the page follows the device's setting.
try {
  const theme = localStorage.getItem("fc.theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch { /* storage blocked: follow the device */ }
