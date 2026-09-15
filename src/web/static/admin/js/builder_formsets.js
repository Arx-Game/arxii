// Shared clone-a-formset-row helpers for the Upbringing Builder (#3660) and the
// tradition slate page (#3675): both pages' "Add X" buttons clone a formset's
// own empty form client-side, since there is no saved row to fetch an admin
// fragment for until the whole page is saved.
//
// Exposed as window.arxBuilderFormsets so each page's own inline script wires
// its own buttons/targets/prefixes without re-implementing these three
// functions (#3675 review: the tradition slate page had shipped a verbatim
// copy of the Upbringing Builder's script).
(function () {
  "use strict";

  // Bumps a formset's TOTAL_FORMS management field and returns the fresh
  // index a cloned row should use in place of "__prefix__".
  function nextFormIndex(prefix) {
    var totalInput = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
    var index = parseInt(totalInput.value, 10);
    totalInput.value = String(index + 1);
    return index;
  }

  // Django's own admin/js/autocomplete.js only initializes select2 on load and
  // on this event - a row cloned client-side otherwise carries a plain,
  // uninitialized <select> for every autocomplete widget it contains.
  // Dispatching this on the inserted element itself, with bubbles set, matches
  // what autocomplete.js's document-level listener reads off event.target
  // ($(event.target).find('.admin-autocomplete')).
  function announceFormsetAdded(prefix, row) {
    row.dispatchEvent(
      new CustomEvent("formset:added", { bubbles: true, detail: { formsetName: prefix } })
    );
  }

  // Clones a <template>'s content, swapping "__prefix__" for `index`, and
  // returns the new element's first child. `wrapperTag` picks the parsing
  // context: "div" (the default) for a whole panel, "tbody" for a bare <tr> -
  // a <tr> parsed while assigned to a plain <div>'s innerHTML is silently
  // dropped by the browser's own HTML parser, since a <tr> is only valid
  // inside a table.
  function cloneFromTemplate(templateId, index, wrapperTag) {
    var tpl = document.getElementById(templateId);
    var html = tpl.innerHTML.split("__prefix__").join(String(index));
    var holder = document.createElement(wrapperTag || "div");
    holder.innerHTML = html;
    return holder.firstElementChild;
  }

  window.arxBuilderFormsets = {
    nextFormIndex: nextFormIndex,
    announceFormsetAdded: announceFormsetAdded,
    cloneFromTemplate: cloneFromTemplate,
  };
})();
