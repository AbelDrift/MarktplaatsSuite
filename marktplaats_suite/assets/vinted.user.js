// ==UserScript==
// @name         Marktplaats Suite → Vinted
// @namespace    marktplaats-suite
// @version      1.0
// @description  Vult het Vinted-formulier (titel, beschrijving, categorie, merk, staat, kleur, materiaal, prijs, pakketformaat) in met gegevens uit SellYourShit. Foto's voeg je zelf toe.
// @match        https://www.vinted.nl/*
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
      <label style="display:block;margin-top:6px"><input type="checkbox" id="msw-auto" checked> Vul automatisch in zodra er foto's staan</label>
      <button id="msw-nu" style="margin-top:6px;width:100%">Vul formulier nu in</button>
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
      o.textContent = (p.al_online_vinted ? '✓ ' : '') + p.artikelnummer + ' – ' + (p.titel || '').slice(0, 40);
      s.appendChild(o);
    }
    producten.sort((a, b) => (a.al_online_vinted - b.al_online_vinted) || ((!a.voor_vinted) - (!b.voor_vinted)));
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
  function veldViaAttribuut(label) {
    const t = norm(label).replace(/^[a-c]:\s*/, '');
    return [...document.querySelectorAll(VELD)].find(f => !paneel.contains(f) && zichtbaar(f) &&
      [f.placeholder, f.getAttribute('aria-label'), f.name, f.id].some(a => norm(a).includes(t))) || null;
  }
  function vulVeld(label, waarde, begin) {
    const v = veldNaLabel(label, begin) || veldNaLabel(label.replace(/^[A-C]:\s*/, ''), true) || veldViaAttribuut(label);
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

  // ------------------------------------------------------------ Vinted-stappen
  const huidig = () => producten.find(p => p.artikelnummer === gekozen);
  const STAAT_MAP = { 'nieuwstaat': 'Nieuw zonder prijskaartje', 'zo goed als nieuw': 'Heel goed', 'gebruikt': 'Goed', 'beschadigd': 'Voldoende' };
  const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
  const lijstje = s => (s || '').split(/[,/&]| en /).map(x => x.trim()).filter(Boolean);

  async function openLijst(label, placeholders) {
    for (const p of placeholders || []) if (klik(p)) { await slaap(600); return true; }
    const labels = zoek(label, true);
    for (let i = labels.length - 1; i >= 0; i--)
      for (const e of document.querySelectorAll('[role=combobox],[role=button],button,input,[aria-haspopup]')) {
        if (paneel.contains(e) || !zichtbaar(e)) continue;
        if (labels[i].compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING) {
          e.scrollIntoView({ block: 'center' }); e.click(); await slaap(600); return true;
        }
      }
    return false;
  }
  async function zoekInLijst(tekst) {
    const f = [...document.querySelectorAll('input[placeholder^="Zoek"]')].find(zichtbaar);
    if (!f) return false;
    f.click(); setWaarde(f, tekst); await slaap(1000);
    return true;
  }
  async function klikOptie(titel, kruimel) {
    for (const el of zoek(titel, false)) {
      if (kruimel && kruimel.length) {
        let o = el;
        for (let i = 0; i < 4 && o.parentElement; i++) { o = o.parentElement; if ((o.innerText || '').length > el.innerText.length + 2) break; }
        const t = (o.innerText || '').toLowerCase();
        if (!kruimel.every(k => t.includes(k.toLowerCase()))) continue;
      }
      el.scrollIntoView({ block: 'center' }); el.click(); await slaap(500);
      return true;
    }
    return false;
  }
  async function sluitLijst() {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    if (!klik('Details')) document.activeElement && document.activeElement.blur();
    await slaap(400);
  }
  async function kiesVoorgestelde() {
    const kop = zoek('Voorgesteld', false)[0];
    if (!kop) return null;
    const eind = zoek('Alle catalogusrubrieken', false)[0];
    const uit = [];
    for (const i of document.querySelectorAll('input[type=radio],input[type=checkbox],[role=radio],[role=option]')) {
      if (!(kop.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      if (eind && (eind.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      let o = i;
      for (let n = 0; n < 4 && o.parentElement; n++) { o = o.parentElement; if ((o.innerText || '').trim().includes('\n')) break; }
      uit.push([i, (o.innerText || '').trim()]);
    }
    if (!uit.length) return null;
    let gekozen = uit[0];
    for (const [inp, t] of uit) {
      const regels = t.split('\n').map(r => r.trim().toLowerCase()).filter(Boolean);
      if (regels.length > 1 && regels[1].startsWith('home')) { gekozen = [inp, t]; break; }
    }
    gekozen[0].click(); await slaap(500);
    return gekozen[1].replace(/\n/g, ' — ');
  }

  async function tekst(p) {
    if (p.titel && vulVeld('Titel', (p.titel || '').slice(0, 80))) log('✅ Titel');
    if (p.vinted_omschrijving && vulVeld('Beschrijving', p.vinted_omschrijving)) log('✅ Beschrijving');
  }
  async function details(p) {
    const cat = (p.vinted_categorie || '').trim();
    if (await openLijst('Categorie', ['Kies een categorie'])) {
      let gelukt = false;
      if (cat) {
        const delen = cat.split('>').map(x => x.trim()).filter(Boolean);
        const titel = delen[delen.length - 1], kruimel = delen.slice(0, -1);
        await zoekInLijst(titel);
        gelukt = (await klikOptie(titel, kruimel)) || (await klikOptie(titel));
        if (gelukt) log('✅ Categorie: ' + titel);
        else { log(`⚠️ Categorie '${cat}' staat niet zo op Vinted; ik probeer de suggestie van Vinted`);
               await zoekInLijst(''); await slaap(500); }
      }
      if (!gelukt) {
        const g = await kiesVoorgestelde();
        if (g) log(`✅ Categorie (suggestie van Vinted): ${g} — controleer of die klopt`);
        else log('⚠️ Geen categorie gekozen; kies zelf een categorie');
      }
      await sluitLijst();
      await slaap(500);
    }
    await slaap(1000);
    const merk = (p.merk || '').trim() || 'Geen merk';
    if (await openLijst('Merk', ['Selecteer een merk'])) {
      await zoekInLijst(merk);
      log((await klikOptie(merk)) ? '✅ Merk: ' + merk : `⚠️ Merk '${merk}' niet gevonden; kies zelf`);
    }
    const staat = STAAT_MAP[(p.conditie || '').trim().toLowerCase()];
    if (staat) {
      if (await openLijst('Staat', ['Selecteer de staat']))
        log((await klikOptie(staat)) ? '✅ Staat: ' + staat : `⚠️ Staat '${staat}' niet gevonden; kies zelf`);
    } else log('⚠️ Geen staat bekend; kies zelf');
    const kleuren = lijstje(p.kleur).slice(0, 2);
    if (kleuren.length) {
      if (await openLijst('Kleur', ['Kies maximaal 2 kleuren'])) {
        for (const k of kleuren) log((await klikOptie(cap(k))) ? '✅ Kleur: ' + k : `⚠️ Kleur '${k}' niet gevonden`);
        await sluitLijst();
      }
    } else log('⚠️ Geen kleur bekend; kies zelf (verplicht op Vinted)');
    const mats = lijstje(p.materiaal);
    if (mats.length && await openLijst('Materiaal', ['Kies een materiaal'])) {
      for (const m of mats) {
        if (await klikOptie(cap(m))) { log('✅ Materiaal: ' + m); continue; }
        await zoekInLijst(m);
        log((await klikOptie(cap(m))) ? '✅ Materiaal: ' + m : `⚠️ Materiaal '${m}' niet gevonden`);
      }
      await sluitLijst();
    }
  }
  async function prijs(p) {
    if (p.vinted_prijs === undefined) log('⚠️ Geen prijs bekend; vul zelf in');
    else if (vulVeld('Prijs', p.vinted_prijs)) log('✅ Prijs € ' + p.vinted_prijs);
    if (p.vinted_pakket) {
      if (kiesPakket(p.vinted_pakket)) log('✅ Pakketformaat: ' + p.vinted_pakket + ` (${p.hoogte} x ${p.breedte} x ${p.lengte} cm, ${p.gewicht || '?'} kg)`);
      else log(`⚠️ Pakketformaat '${p.vinted_pakket}' niet gekozen; kies zelf`);
    } else log('⚠️ Afmetingen onvolledig; kies het pakketformaat zelf (Vinted stelt Groot voor)');
  }
  function kiesPakket(naam) {
    for (const el of zoek(naam, false)) {
      let o = el;
      for (let i = 0; i < 6 && o; i++, o = o.parentElement) {
        const r = o.querySelector('input[type=radio],[role=radio]');
        if (r) { r.scrollIntoView({ block: 'center' }); r.click(); return true; }
      }
    }
    return false;
  }
  const _gew = g => { const n = parseFloat(String(g).replace(',', '.')); return isFinite(n) && n > 0 ? n : 0; };

  let afgerond = '';
  async function vulAlles(geforceerd) {
    if (bezig) return;
    const p = huidig();
    if (!p) { if (geforceerd) log('Geen product gekozen'); return; }
    if (!geforceerd && afgerond === p.artikelnummer) return;
    bezig = true; afgerond = p.artikelnummer;
    try {
      log('▶ Formulier invullen…');
      await tekst(p); await details(p); await prijs(p);
      await slaap(800);
      const meld = [...new Set((document.body.innerText.match(/Vul je [a-zé ]+ in om verder te gaan|Prijs moet minimaal [\d.,]+ zijn/g) || []))];
      meld.forEach(m => log('⚠️ Vinted meldt: ' + m));
      log('📝 Klaar. Controleer alles (vooral de categorie) en klik zelf op "Toevoegen".');
    } catch (e) { log('⚠️ Fout: ' + e.message); }
    bezig = false;
  }
  const aantalFotos = () => [...document.querySelectorAll('img')].filter(i => i.offsetWidth > 40 &&
      /^blob:|vinted/i.test(i.src) && !/logo|icon|avatar/i.test(i.src) && !paneel.contains(i)).length;
  let vorig = -1, stabiel = 0;
  setInterval(() => {
    if (!$('msw-auto').checked || bezig || !location.pathname.includes('items/new')) return;
    const n = aantalFotos();
    stabiel = (n > 0 && n === vorig) ? stabiel + 1 : 0;
    vorig = n;
    if (n > 0 && stabiel >= 4) vulAlles(false);
  }, 1500);
  $('msw-nu').onclick = () => vulAlles(true);

  vulSelect();
  ophalen();
})();
