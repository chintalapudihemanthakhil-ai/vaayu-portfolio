(() => {
  const $ = (id) => document.getElementById(id);

  const drawer = $("drawer");
  const hamburger = $("hamburger");
  const drawerClose = $("drawerClose");
  const drawerBackdrop = $("drawerBackdrop");

  function openDrawer() {
    drawer.setAttribute("aria-hidden", "false");
    hamburger.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
  }
  function closeDrawer() {
    drawer.setAttribute("aria-hidden", "true");
    hamburger.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
  }

  hamburger?.addEventListener("click", () => {
    const isHidden = drawer.getAttribute("aria-hidden") !== "false";
    isHidden ? openDrawer() : closeDrawer();
  });
  drawerClose?.addEventListener("click", closeDrawer);
  drawerBackdrop?.addEventListener("click", closeDrawer);

  drawer?.addEventListener("click", (e) => {
    const t = e.target;
    if (t && t.classList && t.classList.contains("drawerLink")) closeDrawer();
  });

  document.addEventListener("click", (e) => {
    const a = e.target.closest?.("a[href^='#']");
    if (!a) return;
    const href = a.getAttribute("href");
    if (!href || href === "#") return;
    const el = document.querySelector(href);
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  });
})();
