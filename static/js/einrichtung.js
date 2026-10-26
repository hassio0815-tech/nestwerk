// Nach jedem Schrittwechsel an den Seitenanfang scrollen.
document.body.addEventListener("htmx:afterSwap", function (e) {
  if (e.detail.target && e.detail.target.id === "assistent") {
    window.scrollTo(0, 0);
  }
});
