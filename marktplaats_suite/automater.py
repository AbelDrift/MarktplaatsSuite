#!/usr/bin/env python3
"""
Marktplaats Automatisering - GTK Versie
Alle instellingen binnen de GUI
"""

import os
from marktplaats_suite.common import data_dir, asset, get_xml_path, TabBasis, run_standalone
import sys
import time
import threading
import re
import json
import subprocess
from pathlib import Path

# GTK imports - deze komen van de systeem packages (python3-gi)
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk, Gdk, Pango, GLib, GdkPixbuf

# Probeer selenium te importeren
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError as e:
    print(f"❌ Fout: {e}")
    print("📌 Installeer selenium met: pip install selenium")
    raise

# ============================================
# CONFIGURATIE BESTAND
# ============================================

class ConfigManager:
    def __init__(self, config_file=None):
        self.config_file = config_file or os.path.join(data_dir(), "automater_config.json")
        self.config = self._load()

    def _load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                return self._default_config()
        return self._default_config()

    def _default_config(self):
        return {
            "storage": {
                "xml_path": ""
            },
            "chrome": {
                "user_data_dir": os.path.expanduser("~/.config/google-chrome"),
                "profile": "Default"
            },
            "paths": {
                "base_image_path": os.path.expanduser("~/Afbeeldingen")
            },
            "preferences": {
                "max_title_length": 60,
                "wait_between_products": 3
            }
        }

    def save(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Fout bij opslaan: {e}")
            return False

    def get(self, key, default=None):
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key, value):
        keys = key.split('.')
        target = self.config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save()

# ============================================
# LOGGING
# ============================================

class Logger:
    def __init__(self, text_view=None):
        self.text_view = text_view
        self.buffer = None
        if text_view:
            self.buffer = text_view.get_buffer()

    def log(self, msg, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {level}: {msg}\n"
        print(formatted, end="")
        if self.buffer:
            # GTK is niet thread-safe. Het hele plaats-proces draait in een
            # achtergrondthread, dus rechtstreeks aan self.buffer/text_view
            # zitten (zoals hier eerder gebeurde, inclusief een handmatige
            # Gtk.main_iteration()-pomp) is een klassieke oorzaak van
            # willekeurige, moeilijk te reproduceren crashes. Via
            # GLib.idle_add gebeurt de daadwerkelijke widget-aanpassing
            # altijd op de GTK-hoofdthread.
            GLib.idle_add(self._append_to_buffer, formatted)

    def _append_to_buffer(self, formatted):
        end_iter = self.buffer.get_end_iter()
        self.buffer.insert(end_iter, formatted)
        mark = self.buffer.create_mark(None, self.buffer.get_end_iter(), False)
        self.text_view.scroll_to_mark(mark, 0.0, True, 0.0, 0.0)
        return False  # eenmalige idle-callback, niet herhalen

    def info(self, msg): self.log(msg, "INFO")
    def warning(self, msg): self.log(msg, "⚠️")
    def error(self, msg): self.log(msg, "❌")
    def success(self, msg): self.log(f"✅ {msg}", "SUCCESS")
    def step(self, num, msg): self.log(f"📍 Stap {num}: {msg}", "STEP")

# ============================================
# ALGEMENE VOORWAARDEN
# ============================================

ALGEMENE_VOORWAARDEN = """Algemene voorwaarden:
Wij zijn een kleine kringloopwinkel en proberen z.s.m. te reageren. Soms is het heel druk in de winkel en lukt dit niet dezelfde dag.

De richtprijs van een product baseren wij op bestaand aanbod en staat van het artikel met minimum/maximum schatting.

Graag alleen biedingen plaatsen via de bied optie van marktplaats. Advertenties laten we vaak minimaal 2 weken online staan voordat we akkoord gaan met het hoogste aannemelijke bod. Bedankt voor uw begrip 🙏🏻

Als wij akkoord gaan met uw bod, reserveren wij het product maximaal een week voor u. U kunt het product ophalen en afrekenen in onze winkel.

U bent altijd welkom in onze winkel, maar langskomen voor de Marktplaats advertenties zonder afspraak wordt niet op prijs gesteld. Dit gaat altijd via specifieke medewerkers.

Let op: Bij ophalen in de winkel vervalt het herroepingsrecht en kun je het product ter plekke testen.

Ons adres:
Kringloop HerNieuw
Willem Beukelszstraat 6B
3261 LV Oud-Beijerland

Openingstijden Kringloop:
Dinsdag t/m vrijdag 10.00 – 16.00 uur
Zaterdag 10:00-13:00 uur
Zondag en maandag Gesloten"""

# Kolomvolgorde - identiek aan marktplaats_productmanager.py, zodat
# beide apps dezelfde Sheet/XML kunnen lezen/schrijven.
COLUMNS = [
    "artikelnummer", "titel", "categorie", "omschrijving", "online",
    "lengte", "breedte", "hoogte", "gewicht", "conditie", "staat_details",
    "waarde_min", "waarde_max", "vraagprijs", "aanmaakdatum", "aanmaaktijd",
    "tijdsperiode", "opslaglocatie", "sublocatie", "rij", "folder_locatie",
    "verkocht", "verkoopprijs", "verkoopdatum", "algemene_voorwaarden",
    "url_1", "url_2", "url_3", "url_4", "url_5",
    "leverwijze", "klant_naam", "klant_telefoon", "klant_email",
    "ophaal_afspraak", "track_trace", "verwerkt_door", "toegewezen_aan",
]
COL = {naam: idx for idx, naam in enumerate(COLUMNS)}

def build_description(product):
    row = product.get("row", [])
    def col(naam):
        # Naam-gebaseerde lookup i.p.v. magische kolomnummers - die braken
        # eerder al eens stilletjes toen het schema (aanmaaktijd, url_1-5)
        # veranderde zonder dat de indices hier werden bijgewerkt.
        idx = COL.get(naam)
        if idx is None or len(row) <= idx or not row[idx]:
            return ""
        return row[idx].strip()

    # Als marktplaats_productmanager.py al een kant-en-klare, opgemaakte
    # omschrijving.txt in de artikelnummer-map heeft gezet, gebruik die
    # rechtstreeks - dat is dan de enige plek waar de opmaak wordt beheerd.
    folder_locatie = col("folder_locatie")
    if folder_locatie:
        txt_path = os.path.join(folder_locatie, "omschrijving.txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    inhoud = f.read().strip()
                if inhoud:
                    return inhoud
            except Exception:
                pass  # val terug op de kolom-opbouw hieronder

    titel = product.get("titel", "")
    artikelnummer = col("artikelnummer")
    omschrijving = col("omschrijving")
    lengte = col("lengte")
    breedte = col("breedte")
    hoogte = col("hoogte")
    gewicht = col("gewicht")
    conditie = col("conditie")
    schades = col("staat_details")
    waarde = col("waarde_min")
    waarde_extra = col("waarde_max")
    voorwaarden = col("algemene_voorwaarden")

    parts = []
    if titel:
        parts.append(titel)
    if omschrijving:
        parts.append(omschrijving)

    specs = []
    if lengte or breedte or hoogte or gewicht:
        dims = [f"{x}cm" for x in (lengte, breedte, hoogte) if x]
        line = f"* Afmeting (LxBxH & G): {' x '.join(dims)}"
        if gewicht:
            line += f" & {gewicht} kg"
        specs.append(line)
    if conditie:
        specs.append(f"* Conditie/Staat: {conditie}")
    if schades:
        specs.append(f"* Schades: {schades}")
    if waarde:
        line = f"* Waarde: {waarde}"
        if waarde_extra:
            line += f" ~{waarde_extra}"
        specs.append(line)
    if artikelnummer:
        specs.append(f"* Artikelnummer: {artikelnummer}")
    if specs:
        parts.append("\n".join(specs))

    from marktplaats_suite.voorwaarden import voorwaarden_voor_advertentie
    eind = voorwaarden or voorwaarden_voor_advertentie()
    if eind:
        parts.append(eind)
    return "\n\n".join(parts)

# ============================================
# MARKTPLAATS AUTOMATOR
# ============================================

class MarktplaatsAuto:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.driver = None
        self.wait = None
        self.running = False
        self.products = []
        self.pending = []
        self.current = None
        self.step = 0
        self.wait_for_user = False
        self.was_skipped = False
        self.on_wait_for_user = None
        self.user_logged_in = False

    def start_chrome(self):
        self.logger.info("🚀 Start Chrome...")
        options = Options()
        chrome_config = self.config.get('chrome', {})
        user_data_dir = chrome_config.get('user_data_dir', os.path.expanduser("~/.config/google-chrome"))
        profile = chrome_config.get('profile', "Default")

        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')

        try:
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 15)
            self.logger.success("Chrome gestart!")
            return True
        except Exception as e:
            self.logger.error(f"Chrome fout: {e}")
            self.logger.info("💡 Zorg dat Chrome niet open staat en probeer opnieuw")
            return False

    def wait_for_manual_login(self):
        self.logger.info("=" * 50)
        self.logger.info("🔑 LOG IN OP MARKTPLAATS")
        self.logger.info("=" * 50)
        self.logger.info("📌 Open de browser en log handmatig in op Marktplaats")
        self.logger.info("📌 Na het inloggen, klik op de knop 'Ingelogd' in de GUI")
        self.logger.info("=" * 50)

        self.driver.get("https://www.marktplaats.nl")
        time.sleep(2)

        while not self.user_logged_in and self.running:
            time.sleep(0.5)

        if not self.running:
            return False

        self.logger.success("✅ Gebruiker heeft ingelogd!")
        time.sleep(2)
        return True

    def load_products(self):
        self.logger.info("📄 Laden uit lokaal XML-bestand...")
        xml_path = get_xml_path()
        if not xml_path:
            self.logger.error("XML-pad niet ingesteld!")
            return False
        if not os.path.exists(xml_path):
            self.logger.error(f"XML-bestand niet gevonden: {xml_path}")
            return False

        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(xml_path)
            root = tree.getroot()

            rows = []
            for idx, prod_el in enumerate(root.findall("product"), start=2):
                row = []
                for c in COLUMNS:
                    el = prod_el.find(c)
                    row.append(el.text if el is not None and el.text else "")

                artikelnummer = row[COL["artikelnummer"]].strip() if row[COL["artikelnummer"]] else ""
                titel = row[COL["titel"]].strip() if len(row) > COL["titel"] and row[COL["titel"]] else ""
                categorie = row[COL["categorie"]].strip() if len(row) > COL["categorie"] and row[COL["categorie"]] else ""
                online = row[COL["online"]].strip().lower() if len(row) > COL["online"] and row[COL["online"]] else ""
                verkocht = row[COL["verkocht"]].strip().lower() if len(row) > COL["verkocht"] and row[COL["verkocht"]] else ""

                if verkocht == "ja" or online == "ja":
                    continue  # al online staande of verkochte producten niet opnieuw plaatsen

                if artikelnummer and titel:
                    rows.append({
                        "rij": idx,
                        "artikelnummer": artikelnummer,
                        "titel": titel,
                        "categorie": categorie or titel,
                        "row": row
                    })

            self.products = rows
            self.pending = rows.copy()
            self.logger.info(f"✅ {len(rows)} producten geladen uit XML")
            return True

        except Exception as e:
            self.logger.error(f"Fout bij laden uit XML: {e}")
            return False

    def process_products(self):
        total = len(self.pending)
        processed = 0

        for product in self.pending:
            if not self.running:
                break

            processed += 1
            self.current = product
            self.logger.info(f"\n{'='*50}")
            self.logger.info(f"📦 Product {processed}/{total}: {product['artikelnummer']}")
            self.logger.info(f"📝 Titel: {product['titel']}")
            self.logger.info(f"{'='*50}")

            if not self.process_one_product(product):
                self.logger.warning(f"⏭️ Product {product['artikelnummer']} overgeslagen")
                continue

            if processed < total and self.running:
                wait_time = self.config.get('preferences.wait_between_products', 3)
                self.logger.info(f"⏳ Wacht {wait_time} seconden...")
                time.sleep(wait_time)

        if self.running:
            self.logger.success(f"🎉 Alle {processed} producten verwerkt!")
        else:
            self.logger.info(f"⏹️ Gestopt na {processed} producten")

    def process_one_product(self, product):
        try:
            self.step = 1
            self.logger.step(self.step, "Naar plaats pagina")
            self.driver.get("https://www.marktplaats.nl/plaats")
            time.sleep(2)

            self.step = 2
            self.logger.step(self.step, "Categorie invullen")
            max_len = self.config.get('preferences.max_title_length', 60)
            cat = product['categorie'][:max_len].strip()
            cat = re.sub(r'[^\x00-\x7F]+', '', cat)

            try:
                cat_field = self.driver.find_element(By.CSS_SELECTOR,
                    "input[placeholder*='Categorie'], input[placeholder*='categorie']")
            except:
                cat_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='keywords']")

            cat_field.clear()
            cat_field.send_keys(cat)
            time.sleep(0.3)
            cat_field.send_keys(Keys.ENTER)
            time.sleep(1)
            self.logger.info(f"   ✅ Categorie: {cat}")

            self.step = 3
            self.logger.step(self.step, "Titel invullen")
            title = product['titel'][:max_len].strip()
            title = re.sub(r'[^\x00-\x7F]+', '', title)

            title_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "keywords"))
            )
            title_field.clear()
            title_field.send_keys(title)
            time.sleep(0.3)
            title_field.send_keys(Keys.ENTER)
            time.sleep(1)

            actions = ActionChains(self.driver)
            for _ in range(4):
                actions.send_keys(Keys.TAB)
                time.sleep(0.2)
            actions.send_keys(Keys.ENTER).perform()
            time.sleep(2)
            self.logger.info(f"   ✅ Titel: {title}")

            self.step = 4
            self.logger.step(self.step, "Foto's uploaden")
            base_path = self.config.get('paths.base_image_path', os.path.expanduser("~/Afbeeldingen"))
            folder = os.path.join(base_path, product['artikelnummer'], "met_logo")
            images = []
            if os.path.exists(folder):
                for f in os.listdir(folder):
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                        images.append(os.path.join(folder, f))
            images.sort()

            if images:
                file_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                file_input.send_keys("\n".join(images[:10]))
                time.sleep(5)
                self.logger.info(f"   ✅ {len(images[:10])} foto's geüpload")
            else:
                self.logger.info("   ⚠️ Geen foto's gevonden")

            self.step = 5
            self.logger.step(self.step, "Omschrijving invullen")
            description = build_description(product)

            if description:
                try:
                    desc_field = self.wait.until(
                        EC.presence_of_element_located((
                            By.CSS_SELECTOR,
                            "div.RichTextEditor-module-editorInput[data-testid='text-editor-input_nl-NL']"
                        ))
                    )
                    desc_field.click()
                    time.sleep(0.3)

                    for line in description.split("\n"):
                        if line.strip():
                            self.driver.execute_script(
                                "document.execCommand('insertText', false, arguments[0]);",
                                line
                            )
                        desc_field.send_keys(Keys.ENTER)
                        time.sleep(0.05)

                    self.logger.info("   ✅ Omschrijving ingevuld")
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Omschrijving invullen mislukt: {e}")
            else:
                self.logger.info("   ⚠️ Geen omschrijving-data gevonden, overgeslagen")

            self.step = 6
            self.logger.step(self.step, "Wacht op gebruiker")
            self.logger.info("")
            self.logger.info("📝 ADVERTENTIE IS BIJNA KLAAR!")
            self.logger.info("📝 Maak de advertentie handmatig af:")
            self.logger.info("   1. Controleer de beschrijving")
            self.logger.info("   2. Vul eventuele extra velden in")
            self.logger.info("   3. Klik op 'Plaats advertentie'")
            self.logger.info("")
            self.logger.info("⏸️ Klik op 'Volgende' als de advertentie geplaatst is, of 'Overslaan' om dit product bewust over te slaan")

            self.was_skipped = False
            self.wait_for_user = True
            if self.on_wait_for_user:
                self.on_wait_for_user()
            while self.wait_for_user and self.running:
                time.sleep(0.5)

            self.wait_for_user = False
            if self.was_skipped:
                self.logger.warning(f"⏭️ Product {product['artikelnummer']} bewust overgeslagen")
            else:
                self.logger.success(f"✅ Product {product['artikelnummer']} voltooid!")
                try:
                    huidige_url = ""
                    try:
                        huidige_url = self.driver.current_url
                    except Exception:
                        pass
                    self._mark_product_online(product['artikelnummer'], huidige_url)
                    if huidige_url:
                        self.logger.info(f"   📤 Gemarkeerd als 'online', URL opgeslagen: {huidige_url}")
                    else:
                        self.logger.info("   📤 Gemarkeerd als 'online' in de opslag")
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Kon niet als 'online' markeren in de opslag: {e}")
            return True

        except Exception as e:
            self.logger.error(f"Fout bij product {product['artikelnummer']}: {e}")
            return False

    def _mark_product_online(self, artikelnummer, advertentie_url=None):
        """Zet 'online' op ja voor dit product in de XML, zodat een
        volgende uploadsessie dit product overslaat en
        marktplaats_productmanager.py het meteen als online toont. Slaat
        ook de huidige browser-URL op (in het eerste lege url_1..url_5-
        veld), indien gegeven."""
        import xml.etree.ElementTree as ET
        xml_path = get_xml_path()
        if not xml_path or not os.path.exists(xml_path):
            raise FileNotFoundError(f"XML-bestand niet gevonden: {xml_path}")
        tree = ET.parse(xml_path)
        root = tree.getroot()
        gevonden = False
        for prod_el in root.findall("product"):
            nr_el = prod_el.find("artikelnummer")
            if nr_el is not None and (nr_el.text or "").strip() == artikelnummer:
                online_el = prod_el.find("online")
                if online_el is None:
                    online_el = ET.SubElement(prod_el, "online")
                online_el.text = "ja"
                if advertentie_url:
                    # Zet de URL in het eerste lege url_1..url_5-veld (een
                    # product kan op meerdere pagina's tegelijk staan).
                    for slot in ("url_1", "url_2", "url_3", "url_4", "url_5"):
                        slot_el = prod_el.find(slot)
                        bestaande_waarde = (slot_el.text or "").strip() if slot_el is not None else ""
                        if not bestaande_waarde:
                            if slot_el is None:
                                slot_el = ET.SubElement(prod_el, slot)
                            slot_el.text = advertentie_url
                            break
                gevonden = True
                break
        if not gevonden:
            raise ValueError("Artikelnummer niet gevonden in XML")
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    def go_to_next(self):
        self.wait_for_user = False

    def skip_current(self):
        self.was_skipped = True
        try:
            self.logger.info("⏭️ Overslaan - pagina verlaten...")
            self.driver.get("https://www.marktplaats.nl/plaats")
        except Exception as e:
            self.logger.warning(f"Kon niet terugkeren naar plaats-pagina: {e}")
        self.wait_for_user = False

    def stop(self):
        self.running = False

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

# ============================================
# GTK GUI
# ============================================

class App:
    def __init__(self):
        # GTK zet automatisch de juiste WM_CLASS!
        self.window = TabBasis(title="Automater")
        self.window.set_title("Marktplaats Automatisering")
        self.window.set_default_size(1000, 750)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_border_width(10)

        # Zet het icoon (als beschikbaar)
        try:
            icon_path = asset("logo.png")
            if os.path.exists(icon_path):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 64, 64)
                self.window.set_icon(pixbuf)
        except:
            pass

        # Configuratie
        self.config = ConfigManager()
        self.logger = Logger()
        self.auto = MarktplaatsAuto(self.config, self.logger)
        self.auto.on_wait_for_user = self._on_wait_for_user
        self.running = False

        self._setup_ui()
        self._load_config_to_gui()

        self.logger.info("🚀 Klaar om te starten!")
        self.logger.info("📌 Vul eerst de instellingen in en klik op 'Opslaan'")


    def _setup_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.window.add(vbox)

        notebook = Gtk.Notebook()
        vbox.pack_start(notebook, True, True, 0)

        # ===== TAB 1: INSTELLINGEN =====
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        settings_box.set_border_width(10)
        notebook.append_page(settings_box, Gtk.Label(label="⚙️ Instellingen"))

        # Chrome profiel sectie
        label = Gtk.Label()
        label.set_markup("<b>Chrome Profiel</b>")
        label.set_halign(Gtk.Align.START)
        settings_box.pack_start(label, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(5)
        grid.set_margin_bottom(10)
        settings_box.pack_start(grid, False, False, 0)

        label = Gtk.Label(label="Profiel pad:")
        label.set_halign(Gtk.Align.END)
        grid.attach(label, 0, 0, 1, 1)
        self.profile_path_entry = Gtk.Entry()
        self.profile_path_entry.set_hexpand(True)
        grid.attach(self.profile_path_entry, 1, 0, 1, 1)

        label = Gtk.Label(label="Profiel naam:")
        label.set_halign(Gtk.Align.END)
        grid.attach(label, 0, 1, 1, 1)
        self.profile_name_entry = Gtk.Entry()
        grid.attach(self.profile_name_entry, 1, 1, 1, 1)

        # Opslag sectie
        label = Gtk.Label()
        label.set_markup("<b>Opslag (lokaal XML-bestand)</b>")
        label.set_halign(Gtk.Align.START)
        label.set_margin_top(10)
        settings_box.pack_start(label, False, False, 0)

        backend_hint = Gtk.Label()
        backend_hint.set_markup("<small><i>Het XML-bestand stel je centraal in via ⚙️ Instellingen in het hoofdvenster.</i></small>")
        backend_hint.set_halign(Gtk.Align.START)
        settings_box.pack_start(backend_hint, False, False, 0)

        self.xml_path_entry = Gtk.Entry()  # alleen-lezen weergave van het centrale pad
        self.xml_path_entry.set_editable(False)
        self.xml_path_entry.set_hexpand(True)
        settings_box.pack_start(self.xml_path_entry, False, False, 0)

        # Paden sectie
        label = Gtk.Label()
        label.set_markup("<b>Paden</b>")
        label.set_halign(Gtk.Align.START)
        label.set_margin_top(10)
        settings_box.pack_start(label, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(5)
        grid.set_margin_bottom(10)
        settings_box.pack_start(grid, False, False, 0)

        label = Gtk.Label(label="Afbeeldingen pad:")
        label.set_halign(Gtk.Align.END)
        grid.attach(label, 0, 0, 1, 1)
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.image_path_entry = Gtk.Entry()
        self.image_path_entry.set_hexpand(True)
        path_box.pack_start(self.image_path_entry, True, True, 0)
        browse_path_btn = Gtk.Button(label="Bladeren")
        browse_path_btn.connect("clicked", self._browse_path)
        path_box.pack_start(browse_path_btn, False, False, 0)
        grid.attach(path_box, 1, 0, 1, 1)

        # Voorkeuren sectie
        label = Gtk.Label()
        label.set_markup("<b>Voorkeuren</b>")
        label.set_halign(Gtk.Align.START)
        label.set_margin_top(10)
        settings_box.pack_start(label, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(5)
        settings_box.pack_start(grid, False, False, 0)

        label = Gtk.Label(label="Max titel lengte:")
        label.set_halign(Gtk.Align.END)
        grid.attach(label, 0, 0, 1, 1)
        self.max_title_entry = Gtk.Entry()
        self.max_title_entry.set_width_chars(10)
        grid.attach(self.max_title_entry, 1, 0, 1, 1)

        label = Gtk.Label(label="Wacht tussen producten (sec):")
        label.set_halign(Gtk.Align.END)
        grid.attach(label, 0, 1, 1, 1)
        self.wait_products_entry = Gtk.Entry()
        self.wait_products_entry.set_width_chars(10)
        grid.attach(self.wait_products_entry, 1, 1, 1, 1)

        save_btn = Gtk.Button(label="💾 Opslaan")
        save_btn.connect("clicked", self._save_config)
        settings_box.pack_start(save_btn, False, False, 0)

        # ===== TAB 2: DASHBOARD =====
        dashboard_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        dashboard_box.set_border_width(10)
        notebook.append_page(dashboard_box, Gtk.Label(label="🎮 Dashboard"))

        self.status_label = Gtk.Label()
        self.status_label.set_markup("<span foreground='green'>✅ Klaar</span>")
        dashboard_box.pack_start(self.status_label, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        btn_box.set_halign(Gtk.Align.CENTER)
        dashboard_box.pack_start(btn_box, False, False, 0)

        self.start_btn = Gtk.Button(label="▶️ Start")
        self.start_btn.connect("clicked", self._start)
        btn_box.pack_start(self.start_btn, False, False, 0)

        self.login_btn = Gtk.Button(label="🔑 Ingelogd")
        self.login_btn.set_sensitive(False)
        self.login_btn.connect("clicked", self._logged_in)
        btn_box.pack_start(self.login_btn, False, False, 0)

        self.next_btn = Gtk.Button(label="⏭️ Volgende")
        self.next_btn.set_sensitive(False)
        self.next_btn.connect("clicked", self._next)
        btn_box.pack_start(self.next_btn, False, False, 0)

        self.skip_btn = Gtk.Button(label="⏩ Overslaan")
        self.skip_btn.set_sensitive(False)
        self.skip_btn.connect("clicked", self._skip)
        btn_box.pack_start(self.skip_btn, False, False, 0)

        self.stop_btn = Gtk.Button(label="⏹️ Stop")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", self._stop)
        btn_box.pack_start(self.stop_btn, False, False, 0)

        self.progress_bar = Gtk.ProgressBar()
        dashboard_box.pack_start(self.progress_bar, False, False, 0)
        self.progress_label = Gtk.Label(label="0%")
        dashboard_box.pack_start(self.progress_label, False, False, 0)

        # ===== TAB 3: LOG =====
        log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        log_box.set_border_width(10)
        notebook.append_page(log_box, Gtk.Label(label="📝 Log"))

        log_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        log_btn_box.set_halign(Gtk.Align.START)
        log_box.pack_start(log_btn_box, False, False, 0)

        clear_btn = Gtk.Button(label="🗑️ Wis log")
        clear_btn.connect("clicked", self._clear_log)
        log_btn_box.pack_start(clear_btn, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_box.pack_start(scrolled, True, True, 0)

        self.log_text_view = Gtk.TextView()
        self.log_text_view.set_editable(False)
        self.log_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.log_text_view.modify_font(Pango.FontDescription("Monospace 9"))
        scrolled.add(self.log_text_view)

        self.logger = Logger(self.log_text_view)
        self.auto.logger = self.logger

    def _browse_path(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Selecteer afbeeldingen map",
            parent=self.window.top(),
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.image_path_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def _load_config_to_gui(self):
        storage = self.config.get('storage', {})
        self.xml_path_entry.set_text(get_xml_path())

        chrome = self.config.get('chrome', {})
        self.profile_path_entry.set_text(chrome.get('user_data_dir', os.path.expanduser("~/.config/google-chrome")))
        self.profile_name_entry.set_text(chrome.get('profile', "Default"))

        paths = self.config.get('paths', {})
        self.image_path_entry.set_text(paths.get('base_image_path', os.path.expanduser("~/Afbeeldingen")))

        prefs = self.config.get('preferences', {})
        self.max_title_entry.set_text(str(prefs.get('max_title_length', 60)))
        self.wait_products_entry.set_text(str(prefs.get('wait_between_products', 3)))

    def _save_config(self, widget):
        self.config.set('chrome.user_data_dir', self.profile_path_entry.get_text().strip())
        self.config.set('chrome.profile', self.profile_name_entry.get_text().strip())
        self.config.set('paths.base_image_path', self.image_path_entry.get_text().strip())
        self.config.set('preferences.max_title_length', int(self.max_title_entry.get_text().strip() or 60))
        self.config.set('preferences.wait_between_products', int(self.wait_products_entry.get_text().strip() or 3))

        self.logger.success("✅ Configuratie opgeslagen!")

        dialog = Gtk.MessageDialog(
            parent=self.window.top(),
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Configuratie opgeslagen!"
        )
        dialog.run()
        dialog.destroy()

    def _start(self, widget):
        if self.running:
            return

        self._save_config(widget)

        self.running = True
        self.auto.running = True
        self.auto.user_logged_in = False
        self.start_btn.set_sensitive(False)
        self.login_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(True)
        self.next_btn.set_sensitive(False)
        self.skip_btn.set_sensitive(False)
        self.status_label.set_markup("<span foreground='blue'>🔄 Bezig met starten...</span>")

        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            if not self.auto.start_chrome():
                GLib.idle_add(self._on_error, "Chrome starten mislukt")
                return

            GLib.idle_add(self._update_status, "🔑 Wacht op inloggen...")

            if not self.auto.wait_for_manual_login():
                GLib.idle_add(self._on_error, "Inloggen geannuleerd")
                return

            if not self.auto.load_products():
                GLib.idle_add(self._on_error, "Geen producten gevonden")
                return

            GLib.idle_add(self._update_status, "🔄 Bezig met verwerken...")
            self.auto.process_products()
            GLib.idle_add(self._on_finished)

        except Exception as e:
            GLib.idle_add(self._on_error, str(e))

    def _logged_in(self, widget):
        self.auto.user_logged_in = True
        self.login_btn.set_sensitive(False)
        self.logger.info("✅ Ingelogd bevestigd!")

    def _next(self, widget):
        self.next_btn.set_sensitive(False)
        self.skip_btn.set_sensitive(False)
        self.logger.info("⏭️ Door naar volgende...")
        self.auto.go_to_next()

    def _skip(self, widget):
        self.next_btn.set_sensitive(False)
        self.skip_btn.set_sensitive(False)
        self.logger.info("⏩ Overslaan...")
        threading.Thread(target=self.auto.skip_current, daemon=True).start()

    def _on_wait_for_user(self):
        GLib.idle_add(self._enable_next)

    def _stop(self, widget):
        self.running = False
        self.auto.running = False
        self.auto.stop()
        self.start_btn.set_sensitive(True)
        self.login_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(False)
        self.next_btn.set_sensitive(False)
        self.skip_btn.set_sensitive(False)
        self.status_label.set_markup("<span foreground='red'>⏹️ Gestopt</span>")
        self.logger.info("⏹️ Gestopt door gebruiker")

    def _enable_next(self):
        self.next_btn.set_sensitive(True)
        self.skip_btn.set_sensitive(True)

    def _update_status(self, msg):
        self.status_label.set_markup(f"<span foreground='blue'>{msg}</span>")

    def _on_error(self, msg):
        self.logger.error(f"❌ {msg}")
        self.status_label.set_markup(f"<span foreground='red'>❌ Fout: {msg}</span>")
        self.start_btn.set_sensitive(True)
        self.login_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(False)
        self.next_btn.set_sensitive(False)
        self.skip_btn.set_sensitive(False)
        self.running = False

    def _on_finished(self):
        self.logger.success("🎉 Alle producten verwerkt!")
        self.status_label.set_markup("<span foreground='green'>✅ Klaar!</span>")
        self.start_btn.set_sensitive(True)
        self.login_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(False)
        self.next_btn.set_sensitive(False)
        self.skip_btn.set_sensitive(False)
        self.running = False

    def _clear_log(self, widget):
        buffer = self.log_text_view.get_buffer()
        buffer.set_text("")
        self.logger.info("🗑️ Log gewist")

    def kan_sluiten(self):
        """True als afsluiten mag; vraagt bevestiging als de automatisering draait."""
        if self.running:
            dialog = Gtk.MessageDialog(
                parent=self.window.top(),
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Automatisering draait nog. Echt afsluiten?"
            )
            response = dialog.run()
            dialog.destroy()
            if response == Gtk.ResponseType.NO:
                return False
        return True

    def sluit(self):
        try:
            self.auto.close()
        except Exception:
            pass


# ============================================
# MAIN
# ============================================

def main():
    run_standalone(lambda: App().window, "Marktplaats Automatisering", 1000, 750)


if __name__ == "__main__":
    main()
