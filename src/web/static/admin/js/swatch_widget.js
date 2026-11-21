/*
 * The colour picker beside a trait option's colour field (#5241).
 *
 * The field itself stays a text input, because an option that is not a colour
 * leaves it blank and a browser colour input can never be blank. This puts a
 * colour input after every text input marked `data-swatch`, and keeps the two in
 * step: picking a colour writes its #rrggbb into the text input, and typing a
 * valid #rrggbb moves the picker. The picker has no name, so only the text
 * input is ever submitted.
 */
(function () {
  'use strict';

  var HEX = /^#[0-9a-fA-F]{6}$/;

  function pair(text) {
    // The inline's hidden template row is cloned for every added row; a picker
    // put on it would be cloned without its listeners.
    if (text.dataset.swatchReady || text.closest('.empty-form')) {
      return;
    }
    text.dataset.swatchReady = '1';
    var picker = document.createElement('input');
    picker.type = 'color';
    picker.className = 'swatch-picker';
    picker.setAttribute('aria-label', 'Pick a colour');
    if (HEX.test(text.value)) {
      picker.value = text.value;
    }
    picker.addEventListener('input', function () {
      text.value = picker.value;
    });
    text.addEventListener('input', function () {
      if (HEX.test(text.value)) {
        picker.value = text.value;
      }
    });
    text.insertAdjacentElement('afterend', picker);
  }

  function scan(root) {
    root.querySelectorAll('input[data-swatch]').forEach(pair);
  }

  document.addEventListener('DOMContentLoaded', function () {
    scan(document);
  });
  // Django fires this on the row an inline's "Add another" just made.
  document.addEventListener('formset:added', function (event) {
    scan(event.target);
  });
})();
