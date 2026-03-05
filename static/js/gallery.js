(() => {
  const modal = document.getElementById("modal");
  const modalImg = document.getElementById("modalImg");
  const modalBackdrop = document.getElementById("modalBackdrop");
  const modalClose = document.getElementById("modalClose");
  const grid = document.getElementById("galleryGrid");

  if (!modal || !modalImg || !grid) return;

  function open(src) {
    modal.setAttribute("aria-hidden", "false");
    modalImg.src = src;
    document.body.style.overflow = "hidden";
  }
  function close() {
    modal.setAttribute("aria-hidden", "true");
    modalImg.src = "";
    document.body.style.overflow = "";
  }

  grid.addEventListener("click", (e) => {
    const img = e.target.closest?.("img.cardImg");
    if (!img) return;
    open(img.dataset.full || img.src);
  });

  modalBackdrop?.addEventListener("click", close);
  modalClose?.addEventListener("click", close);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.getAttribute("aria-hidden") === "false") close();
  });
})();
