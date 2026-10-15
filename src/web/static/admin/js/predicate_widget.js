// The admin predicate rule widget (#4361): draws the mission studio's builder shape
// (AND / OR / NOT groups, a leaf picker, typed parameters) over a hidden textarea of
// predicate JSON. The leaf catalog is the one /api/missions/predicate-leaves/ serves,
// embedded beside each widget by PredicateRuleWidget. Every edit writes the tree back to
// the textarea; the server validates it with the same validate_predicate_tree.
//
// Tree grammar (world/predicates/predicates.py):
//   {}                                  matches everyone
//   {"op": "AND"|"OR"|"NOT", "of": [...]}
//   {"leaf": "<name>", "params": {...}}
(function () {
  "use strict";

  var OPS = ["AND", "OR", "NOT"];

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function button(text, cls, onClick) {
    var b = el("button", "button pred-btn" + (cls ? " " + cls : ""), text);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function parse(text) {
    try {
      var value = JSON.parse(text || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (err) {
      return null;
    }
  }

  function coerce(raw, type) {
    if (type === "int") {
      var n = parseInt(raw, 10);
      return isNaN(n) ? raw : n;
    }
    if (type === "float") {
      var f = parseFloat(raw);
      return isNaN(f) ? raw : f;
    }
    if (type === "bool") { return raw === true || raw === "true"; }
    return raw;
  }

  function Builder(host) {
    this.host = host;
    this.textarea = document.getElementById(host.dataset.target);
    var catalogNode = document.getElementById(host.dataset.catalog);
    this.catalog = catalogNode ? JSON.parse(catalogNode.textContent) : [];
    this.byName = {};
    for (var i = 0; i < this.catalog.length; i++) {
      this.byName[this.catalog[i].name] = this.catalog[i];
    }
    this.tree = parse(this.textarea.value);
    if (this.tree === null) { return; } // unparseable: leave the JSON textarea showing
    this.textarea.hidden = true;
    this.root = el("div", "pred-builder");
    host.appendChild(this.root);
    this.render();
  }

  Builder.prototype.write = function () {
    this.textarea.value = JSON.stringify(this.tree);
  };

  Builder.prototype.changed = function () {
    this.write();
    this.render();
  };

  Builder.prototype.render = function () {
    var self = this;
    this.root.innerHTML = "";
    if (!this.tree || (!this.tree.op && this.tree.leaf === undefined)) {
      var empty = el("div", "pred-empty");
      empty.appendChild(el("span", "pred-note", "Matches everyone."));
      empty.appendChild(button("+ Leaf", "", function () {
        self.tree = { leaf: "", params: {} };
        self.changed();
      }));
      empty.appendChild(button("+ Group", "", function () {
        self.tree = { op: "AND", of: [] };
        self.changed();
      }));
      this.root.appendChild(empty);
      return;
    }
    this.root.appendChild(this.node(this.tree, function (replacement) {
      self.tree = replacement || {};
      self.changed();
    }));
  };

  // Draws one node; `replace(newNode)` swaps it in its parent (null removes it).
  Builder.prototype.node = function (node, replace) {
    return node.op ? this.group(node, replace) : this.leaf(node, replace);
  };

  Builder.prototype.group = function (node, replace) {
    var self = this;
    var box = el("div", "pred pred-grp");
    var head = el("div", "pred-h");
    head.appendChild(el("span", "pred-note", "Operator"));
    var select = el("select", "pred-op");
    OPS.forEach(function (op) {
      var opt = el("option", "", op);
      opt.value = op;
      opt.selected = node.op === op;
      select.appendChild(opt);
    });
    select.addEventListener("change", function () {
      node.op = select.value;
      self.changed();
    });
    head.appendChild(select);
    head.appendChild(button("Remove group", "pred-x", function () { replace(null); }));
    box.appendChild(head);
    var children = node.of || (node.of = []);
    children.forEach(function (child, index) {
      box.appendChild(self.node(child, function (replacement) {
        if (replacement === null) { children.splice(index, 1); } else { children[index] = replacement; }
        self.changed();
      }));
    });
    var adds = el("div", "pred-adds");
    if (node.op !== "NOT" || children.length === 0) {
      adds.appendChild(button("+ Leaf", "", function () {
        children.push({ leaf: "", params: {} });
        self.changed();
      }));
      adds.appendChild(button("+ Group", "", function () {
        children.push({ op: "AND", of: [] });
        self.changed();
      }));
    }
    box.appendChild(adds);
    return box;
  };

  Builder.prototype.leaf = function (node, replace) {
    var self = this;
    var box = el("div", "pred pred-leaf");
    var head = el("div", "pred-h");
    var select = el("select", "pred-leaf-name");
    var blank = el("option", "", "Pick a test");
    blank.value = "";
    select.appendChild(blank);
    this.catalog.forEach(function (entry) {
      var opt = el("option", "", entry.name);
      opt.value = entry.name;
      opt.selected = node.leaf === entry.name;
      select.appendChild(opt);
    });
    select.addEventListener("change", function () {
      node.leaf = select.value;
      node.params = {};
      self.changed();
    });
    head.appendChild(select);
    head.appendChild(button("×", "pred-x", function () { replace(null); }));
    box.appendChild(head);
    var spec = this.byName[node.leaf];
    if (spec && spec.params.length) {
      var params = el("div", "pred-params");
      node.params = node.params || {};
      spec.params.forEach(function (param) {
        params.appendChild(self.param(node, param));
      });
      box.appendChild(params);
    }
    return box;
  };

  Builder.prototype.param = function (node, param) {
    var self = this;
    var label = el("label", "pred-param");
    label.appendChild(el("span", "pred-note", param.name + " (" + param.type + ")"));
    var input;
    if (param.choices) {
      input = el("select", "pred-input");
      var blank = el("option", "", "");
      blank.value = "";
      input.appendChild(blank);
      param.choices.forEach(function (choice) {
        var opt = el("option", "", choice);
        opt.value = choice;
        opt.selected = node.params[param.name] === choice;
        input.appendChild(opt);
      });
    } else {
      input = el("input", "pred-input");
      input.type = param.type === "int" || param.type === "float" ? "number" : "text";
      var current = node.params[param.name];
      input.value = current === undefined || current === null ? "" : String(current);
    }
    input.addEventListener("change", function () {
      node.params[param.name] = coerce(input.value, param.type);
      self.write();
    });
    label.appendChild(input);
    return label;
  };

  function init(scope) {
    var hosts = (scope || document).querySelectorAll(".pred-host");
    for (var i = 0; i < hosts.length; i++) {
      var host = hosts[i];
      // A host inside a <template> is the empty form a "+ Add" button clones.
      if (host.dataset.ready || host.closest("template")) { continue; }
      if (host.dataset.target.indexOf("__prefix__") !== -1) { continue; }
      host.dataset.ready = "1";
      new Builder(host);
    }
  }

  document.addEventListener("DOMContentLoaded", function () { init(document); });
  document.addEventListener("formset:added", function (event) { init(event.target); });
  window.arxPredicateWidget = { init: init };
})();
