import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

const template = readFileSync(
  resolve(process.cwd(), '../src/web/templates/admin/magic/kindling_situation_inline.html'),
  'utf8'
);
const script = template.match(/<script>([\s\S]*?)<\/script>/)?.[1];
if (!script) throw new Error('Kindling inline script missing');

function row(): HTMLTableRowElement {
  const element = document.createElement('tr');
  element.className = 'form-row';
  element.innerHTML =
    '<td class="field-situation"><select><option value="social">Social</option><option value="combat">Combat</option></select></td><td><span class="kp" data-param="threshold"><input value=""></span><span class="kp" data-param="affinity"><input value=""></span><span class="kp-none">None</span></td>';
  return element;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('kindling admin inline parameters', () => {
  it('shows allowed or populated fields on changes and newly added rows', () => {
    document.body.innerHTML =
      '<script id="kindling-param-map" type="application/json">{"social":["threshold"],"combat":["affinity"]}</script><table id="kindling-group"><tbody></tbody></table>';
    const group = document.querySelector('#kindling-group tbody')!;
    const first = row();
    group.append(first);
    new Function(script.replace('{{ inline_admin_formset.formset.prefix }}', 'kindling'))();
    const threshold = first.querySelector<HTMLElement>('[data-param="threshold"]')!;
    const affinity = first.querySelector<HTMLElement>('[data-param="affinity"]')!;
    const select = first.querySelector('select')!;
    expect(threshold.hidden).toBe(false);
    expect(affinity.hidden).toBe(true);

    threshold.querySelector('input')!.value = '5';
    select.value = 'combat';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    expect(threshold.hidden).toBe(false);
    expect(affinity.hidden).toBe(false);

    threshold.querySelector('input')!.value = '';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    expect(threshold.hidden).toBe(true);
    expect(affinity.hidden).toBe(false);

    const added = row();
    group.append(added);
    added.dispatchEvent(new Event('formset:added', { bubbles: true }));
    expect(added.querySelector<HTMLElement>('[data-param="threshold"]')!.hidden).toBe(false);
    expect(added.querySelector<HTMLElement>('[data-param="affinity"]')!.hidden).toBe(true);
  });
});
