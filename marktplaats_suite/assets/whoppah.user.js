// ==UserScript==
// @name         Marktplaats Suite → Whoppah
// @namespace    marktplaats-suite
// @version      1.0
// @description  Vult de Whoppah-stappen (details, maten, prijs, verzending) in met gegevens uit SellYourShit. Foto's voeg je zelf toe.
// @match        https://www.whoppah.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';
  if (window.top !== window.self) return;
  const PORT = 8765;
  const slaap = ms => new Promise(r => setTimeout(r, ms));
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const ontvangen = (k, d) => { try { const v = GM_getValue(k); return v === undefined ? d : v; } catch (e) { return d; } };
  const bewaar = (k, v) => { try { GM_setValue(k, v); } catch (e) {} };

  let producten = ontvangen('producten', []);
  let gekozen = ontvangen('gekozen', '');
  let bezig = false;
  const klaar = {};            // `${artikel}:${stap}` -> true

  // ------------------------------------------------------------ paneel
  const paneel = document.createElement('div');
  paneel.id = 'msw-paneel';
  paneel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;width:300px;background:#1f2933;' +
    'color:#e8eef3;font:12px/1.4 system-ui,sans-serif;border-radius:10px;box-shadow:0 4px 18px #0006;padding:10px;';
  paneel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <b>SellYourShit</b><span id="msw-min" style="cursor:pointer;padding:0 4px">–</span></div>
    <div id="msw-body">
      <div style="display:flex;gap:4px"><select id="msw-sel" style="flex:1;min-width:0;color:#000"></select>
        <button id="msw-ver" title="Producten opnieuw ophalen">↻</button></div>
      <label style="display:block;margin-top:6px"><input type="checkbox" id="msw-auto" checked> Vul elke stap automatisch in</label>
      <label style="display:block"><input type="checkbox" id="msw-door" checked> Ga daarna naar de volgende stap</label>
      <button id="msw-nu" style="margin-top:6px;width:100%">Vul deze stap nu in</button>
      <div id="msw-log" style="margin-top:6px;max-height:140px;overflow:auto;background:#0004;padding:4px;border-radius:6px;white-space:pre-wrap"></div>
      <details style="margin-top:6px"><summary>Producten plakken (als ophalen niet lukt)</summary>
        <textarea id="msw-plak" rows="3" style="width:100%;color:#000" placeholder="Plak hier de JSON uit de Suite"></textarea>
        <button id="msw-laad" style="width:100%">Laden</button></details>
    </div>`;
  document.body.appendChild(paneel);
  const $ = id => paneel.querySelector('#' + id);

  function log(t) {
    const l = $('msw-log');
    l.textContent += (l.textContent ? '\n' : '') + t;
    l.scrollTop = l.scrollHeight;
  }
  $('msw-min').onclick = () => { const b = $('msw-body'); b.style.display = b.style.display === 'none' ? '' : 'none'; };

  function vulSelect() {
    const s = $('msw-sel');
    s.innerHTML = '';
    for (const p of producten) {
      const o = document.createElement('option');
      o.value = p.artikelnummer;
      o.textContent = (p.al_online_whoppah ? '✓ ' : '') + p.artikelnummer + ' – ' + (p.titel || '').slice(0, 40);
      s.appendChild(o);
    }
    if (!producten.some(p => p.artikelnummer === gekozen) && producten.length) gekozen = producten[0].artikelnummer;
    s.value = gekozen;
  }
  $('msw-sel').onchange = e => { gekozen = e.target.value; bewaar('gekozen', gekozen); log('Gekozen: ' + gekozen); };

  function ophalen() {
    return new Promise(res => {
      GM_xmlhttpRequest({
        method: 'GET', url: `http://127.0.0.1:${PORT}/producten`, timeout: 5000,
        onload: r => {
          try { producten = JSON.parse(r.responseText); bewaar('producten', producten); vulSelect();
                log(`${producten.length} producten opgehaald`); res(true); }
          catch (e) { log('Antwoord van de Suite niet te lezen'); res(false); }
        },
        onerror: () => { log('Suite niet bereikbaar. Staat de Suite open? (anders: producten plakken)'); res(false); },
        ontimeout: () => { log('Suite reageert niet'); res(false); },
      });
    });
  }
  $('msw-ver').onclick = ophalen;
  $('msw-laad').onclick = () => {
    try { producten = JSON.parse($('msw-plak').value); bewaar('producten', producten); vulSelect(); log(`${producten.length} producten geladen`); }
    catch (e) { log('Dat is geen geldige JSON'); }
  };

  // ------------------------------------------------------------ zoek/klik-hulpjes (tekstgebaseerd)
  const zichtbaar = el => { const r = el.getBoundingClientRect(), st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const eigenTekst = el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  function zoek(tekst, begin) {
    const t = norm(tekst), uit = [];
    for (const el of document.body.querySelectorAll('*')) {
      if (paneel.contains(el) || !zichtbaar(el)) continue;
      const x = norm(eigenTekst(el));
      if (!x) continue;
      if (begin ? x.startsWith(t) : x === t) {
        let kind = false;
        for (const c of el.children) if (norm(eigenTekst(c)) === x && zichtbaar(c)) { kind = true; break; }
        if (!kind) uit.push(el);
      }
    }
    return uit;
  }
  function klik(tekst, begin) {
    const els = zoek(tekst, begin);
    if (!els.length) return false;
    els[0].scrollIntoView({ block: 'center' });
    els[0].click();
    return true;
  }
  const VELD = 'input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=hidden]), textarea, [contenteditable=true]';
  function setWaarde(el, v) {
    el.focus();
    if (el.isContentEditable) { document.execCommand('selectAll'); document.execCommand('insertText', false, String(v)); return; }
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, String(v));
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function veldNaLabel(label, begin) {
    const labels = zoek(label, begin);
    for (let i = labels.length - 1; i >= 0; i--)
      for (const f of document.querySelectorAll(VELD)) {
        if (paneel.contains(f) || !zichtbaar(f)) continue;
        if (labels[i].compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING) return f;
      }
    return null;
  }
  function vulVeld(label, waarde, begin) {
    const v = veldNaLabel(label, begin);
    if (!v) { log(`⚠️ Veld '${label}' niet gevonden`); return false; }
    v.scrollIntoView({ block: 'center' });
    setWaarde(v, waarde);
    return true;
  }
  function schakelaar(label, aan) {
    for (const el of zoek(label, true)) {
      let o = el;
      for (let i = 0; i < 5 && o; i++, o = o.parentElement) {
        const inp = o.querySelector('input[type=checkbox], [role=switch]');
        if (inp) {
          const staat = inp.type === 'checkbox' ? inp.checked : inp.getAttribute('aria-checked') === 'true';
          if (staat !== !!aan) inp.click();
          return true;
        }
      }
    }
    log(`⚠️ Schakelaar '${label}' niet gevonden`);
    return false;
  }
  const isWijzig = b => norm(b.innerText) === 'wijzig';
  function rij(label) {
    for (const l of zoek(label, false)) {
      let o = l;
      for (let i = 0; i < 6 && o; i++, o = o.parentElement) {
        const knoppen = [...o.querySelectorAll('a,button,[role=button]')].filter(b => isWijzig(b) || norm(b.innerText).startsWith('+'));
        if (knoppen.length) {
          let w = eigenTekst(o).replace(/\bwijzig\b/ig, '');
          w = w.replace(new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), '').trim();
          return [o, w];
        }
      }
    }
    return [null, ''];
  }
  function kiesOptie(tekst) {
    for (const el of zoek(tekst, false)) {
      if (['INPUT', 'TEXTAREA'].includes(el.tagName)) continue;
      el.click();
      return true;
    }
    return false;
  }
  async function typInActiefVeld(tekst) {
    let a = document.activeElement;
    if (!(a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable))) {
      a = [...document.querySelectorAll(VELD)].find(f => !paneel.contains(f) && zichtbaar(f) && f.matches(':focus-within, :focus'));
    }
    if (!a) return false;
    setWaarde(a, tekst);
    await slaap(600);
    kiesOptie(tekst);
    return true;
  }
  async function bevestig() {
    for (const t of ['Opslaan', 'Klaar', 'Bevestigen', 'OK', 'Toepassen'])
      for (const el of zoek(t, false))
        if (['BUTTON', 'A'].includes(el.tagName)) { el.click(); return true; }
    return false;
  }
  async function controleerEnPasAan(label, gewenst) {
    if (!gewenst) return;
    const [r, huidig] = rij(label);
    if (!r) { log(`⚠️ Rij '${label}' niet gevonden, controleer zelf`); return; }
    const n = s => norm(s);
    if (n(huidig).includes(n(gewenst))) { log(`✅ ${label}: '${huidig}' klopt al`); return; }
    log(`✏️ ${label}: '${huidig}' → '${gewenst}'`);
    const knop = [...r.querySelectorAll('a,button,[role=button]')].find(isWijzig);
    if (!knop) { log(`⚠️ ${label}: geen Wijzig-knop, pas zelf aan`); return; }
    knop.scrollIntoView({ block: 'center' });
    knop.click();
    await slaap(800);
    if ((await typInActiefVeld(gewenst)) || kiesOptie(gewenst)) {
      await bevestig();
      for (let i = 0; i < 8; i++) {
        await slaap(400);
        const [, nu] = rij(label);
        if (n(nu).includes(n(gewenst))) { log(`✅ ${label} aangepast`); return; }
      }
    }
    log(`⚠️ ${label}: lukte niet automatisch, pas zelf aan naar '${gewenst}'`);
  }

  // ------------------------------------------------------------ stappen
  const huidig = () => producten.find(p => p.artikelnummer === gekozen);
  const lijf = () => norm(document.body.innerText);
  const doorgaan = () => $('msw-door').checked;

  async function stapDetails(p) {
    const merk = (p.merk || '').trim();
    const [r, h] = rij('Merk');
    if (merk) {
      if (r && /niet gevonden|onbekend/i.test(h)) {
        if (klik('+ Merk') && ((await typInActiefVeld(merk)) || kiesOptie(merk))) { await bevestig(); log('✅ Merk: ' + merk); }
        else log(`⚠️ Merk '${merk}' niet automatisch gelukt`);
      } else await controleerEnPasAan('Merk', merk);
    } else if (klik('Weet ik niet')) log("✅ Merk: 'Weet ik niet'");
    await controleerEnPasAan('Titel', (p.titel || '').slice(0, 60));
    await controleerEnPasAan('Stijl', p.stijl);
    await controleerEnPasAan('Kleur', p.kleur);
    await controleerEnPasAan('Materiaal', p.materiaal);
    await controleerEnPasAan('Staat', p.wp_staat);
    const extra = (p.extra_info_koper || '').trim();
    if (extra && vulVeld('Wat moet een koper nog weten?', extra, true)) log('✅ Extra info voor koper');
    if (doorgaan()) { await slaap(400); klik('Ziet er goed uit'); }
  }
  async function stapMaten(p) {
    if (p.wp_breedte === undefined) { log('⚠️ Afmetingen onvolledig, vul zelf in'); return; }
    vulVeld('Breedte', p.wp_breedte); vulVeld('Diepte', p.wp_diepte); vulVeld('Hoogte', p.wp_hoogte);
    log(`✅ Maten ${p.wp_breedte} x ${p.wp_diepte} x ${p.wp_hoogte} cm`);
    if (doorgaan()) { await slaap(400); klik('Volgende'); }
  }
  async function stapPrijs(p) {
    if (p.wp_prijs === undefined) { log('⚠️ Geen vraagprijs, vul zelf in'); return; }
    vulVeld('Vraagprijs', p.wp_prijs);
    klik('Smart Drop', true); await slaap(500);
    klik(p.wp_stap + '%'); klik(p.wp_interval);
    vulVeld('Nooit lager dan', p.wp_ondergrens);
    schakelaar('Biedingen toestaan', p.wp_biedingen);
    log(`✅ Prijs € ${p.wp_prijs}, ondergrens € ${p.wp_ondergrens}`);
    if (doorgaan()) { await slaap(500); klik('Volgende'); }
  }
  async function stapVerzending(p) {
    if (p.wp_verzending) { if (klik(p.wp_verzending, true)) log('✅ Verzending: ' + p.wp_verzending); }
    else log('⚠️ Geen afmetingen, kies verzending zelf');
    schakelaar('Kopers mogen het ook ophalen', p.wp_ophalen);
    if (doorgaan()) { await slaap(500); klik('Volgende: controleren'); }
  }
  const STAPPEN = [
    ['klopt dit?', 'details', stapDetails],
    ['hoe groot is het?', 'maten', stapMaten],
    ['wat wil je ervoor hebben?', 'prijs', stapPrijs],
    ['hoe komt het bij de koper?', 'verzending', stapVerzending],
  ];

  async function vulStap(geforceerd) {
    if (bezig) return;
    const p = huidig();
    if (!p) { if (geforceerd) log('Geen product gekozen'); return; }
    const t = lijf();
    for (const [kenmerk, naam, fn] of STAPPEN) {
      if (!t.includes(kenmerk)) continue;
      const sleutel = p.artikelnummer + ':' + naam;
      if (klaar[sleutel] && !geforceerd) return;
      klaar[sleutel] = true;
      bezig = true;
      try { log(`▶ Stap: ${naam}`); await slaap(1000); await fn(p); }
      catch (e) { log('⚠️ Fout: ' + e.message); }
      bezig = false;
      return;
    }
    if (geforceerd) log('Geen herkend Whoppah-scherm (details, maten, prijs of verzending)');
  }
  $('msw-nu').onclick = () => vulStap(true);
  setInterval(() => { if ($('msw-auto').checked) vulStap(false); }, 1500);

  vulSelect();
  ophalen();
})();
