// The Trial builder page (#4513): live warnings.
//
// The rules that refuse a trial row live on the server (checks.trial_rules, through the
// models' clean methods). This script posts the form to the page's check endpoint a moment
// after each edit and draws what comes back: the rail, and the messages under each tier.
// Nothing here decides anything, so the rail can never disagree with what Save will say.
(function () {
  "use strict";

  var form = document.getElementById("trial-form");
  if (!form) { return; }
  var rail = document.getElementById("tb-rail");
  var timer = null;
  var latest = 0;

  function drawTierErrors(errors) {
    Object.keys(errors).forEach(function (pk) {
      var list = document.getElementById("tier-errors-" + pk);
      if (!list) { return; }
      list.textContent = "";
      errors[pk].forEach(function (message) {
        var item = document.createElement("li");
        item.textContent = message;
        list.appendChild(item);
      });
    });
  }

  function draw(data) {
    // The rail module list sits before the Credit module, which is static.
    var holder = document.createElement("div");
    holder.innerHTML = data.rail;
    var credit = rail.lastElementChild;
    while (rail.firstChild !== credit) { rail.removeChild(rail.firstChild); }
    while (holder.firstChild) { rail.insertBefore(holder.firstChild, credit); }
    drawTierErrors(data.tier_errors);
  }

  function check() {
    var ticket = ++latest;
    fetch(form.dataset.checkUrl, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    }).then(function (response) {
      return response.ok ? response.json() : null;
    }).then(function (data) {
      if (data && ticket === latest) { draw(data); }
    });
  }

  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(check, 250);
  }

  form.addEventListener("input", schedule);
  form.addEventListener("change", schedule);
  // select2 (the autocomplete pickers) announces a pick through jQuery, which a native
  // listener does not hear.
  if (window.django && window.django.jQuery) {
    window.django.jQuery(form).on("change", schedule);
  }

  // Points are not used when a tier grants the technique outright.
  function syncOutright(box) {
    var points = box.closest(".tb-inline").querySelector("input[type=number]");
    if (points) { points.disabled = box.checked; }
  }
  form.querySelectorAll("input[name$='grant_outright']").forEach(function (box) {
    syncOutright(box);
    box.addEventListener("change", function () { syncOutright(box); });
  });

  form.querySelectorAll("[data-confirm]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      if (!window.confirm(button.dataset.confirm)) { event.preventDefault(); }
    });
  });
})();
