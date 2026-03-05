(() => {
  const form = document.getElementById("contactForm");
  const toast = document.getElementById("toast");
  const submit = document.getElementById("contactSubmit");

  if (!form) return;

  function setToast(msg, ok=true){
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.remove("ok","bad");
    toast.classList.add(ok ? "ok" : "bad");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (submit) submit.disabled = true;

    const fd = new FormData(form);
    const payload = {
      name: String(fd.get("name") || ""),
      email: String(fd.get("email") || ""),
      purpose: String(fd.get("purpose") || "Brand Inquiry"),
      message: String(fd.get("message") || "")
    };

    try{
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok){
        const msg = data?.errors?.join(" ") || data?.error || "Something went wrong.";
        setToast(msg, false);
      } else {
        setToast(data?.message || "Sent!", true);
        form.reset();
      }
    } catch {
      setToast("Network error. Please try again.", false);
    } finally {
      if (submit) submit.disabled = false;
      setTimeout(() => setToast(""), 4500);
    }
  });
})();
