// Kept free of React imports so the server-rendered root layout can inline it.
export const THEME_KEY = "aeip.theme";

/** Runs in <head> before first paint so the saved theme never flashes the wrong colours. */
export const themeInitScript = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");` +
  `if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}` +
  `document.documentElement.dataset.theme=t}catch(e){}})();`;
