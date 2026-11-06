"""Offline-rendered native Home Assistant Lovelace dashboards.

The export is deliberately a *user-initiated* operation. It creates two YAML
files in /config using actual Entity Registry IDs; does not create/overwrite
a Lovelace dashboard, modify HA storage, or control Deye.
No frontend add-ons or external services are required.
"""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import indent
from typing import Mapping

FORECAST_CARD_JS = "estadi-energy-pilot-forecast-v040.js"
FORECAST_CARD_RESOURCE = "/local/" + FORECAST_CARD_JS


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _card(content: str) -> str:
    return indent(content.rstrip(), "      ") + "\n"


def _markdown(title: str, content: str) -> str:
    return ("- type: markdown\n"
            + "  title: " + _quote(title) + "\n"
            + "  content: |\n"
            + indent(content.rstrip(), "    ") + "\n")


def _tiles(title: str, items: list[tuple[str, str]], columns: int = 3) -> str:
    if not items:
        return _markdown(title, "Nie znaleziono encji dla tej sekcji.")
    card = ("- type: grid\n"
            + "  title: " + _quote(title) + "\n"
            + "  columns: " + str(columns) + "\n"
            + "  square: false\n"
            + "  cards:\n")
    for name, eid in items:
        card += ("    - type: tile\n"
                 + "      entity: " + _quote(eid) + "\n"
                 + "      name: " + _quote(name) + "\n")
    return card


def _entities(title: str, items: list[tuple[str, str]]) -> str:
    if not items:
        return _markdown(title, "Brak powiązanych encji.")
    card = "- type: entities\n  title: " + _quote(title) + "\n  show_header_toggle: false\n  entities:\n"
    for name, eid in items:
        card += "    - entity: " + _quote(eid) + "\n      name: " + _quote(name) + "\n"
    return card


def _graph(title: str, ids: list[str], hours: int = 24) -> str:
    if not ids:
        return _markdown(title, "Brak skonfigurowanych czujników dla wykresu historii.")
    card = ("- type: history-graph\n"
            + "  title: " + _quote(title) + "\n"
            + "  hours_to_show: " + str(hours) + "\n"
            + "  refresh_interval: 60\n"
            + "  entities:\n")
    for eid in ids:
        card += "    - " + _quote(eid) + "\n"
    return card


def _existing(mapping: Mapping[str, str], labels: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(title, mapping[key]) for title, key in labels if mapping.get(key)]


def render_dashboard(entities: Mapping[str, str], sources: Mapping[str, str]) -> str:
    """Generate one complete native Lovelace dashboard, without guessed IDs."""
    required = ("mini_status", "grid_status", "sim_status", "smart_charge_status")
    missing = [key for key in required if not entities.get(key)]
    if missing:
        raise ValueError("Brak wymaganych encji Energy Pilot: " + ", ".join(missing))

    def eid(key: str) -> str:
        return entities.get(key, "")

    status = eid("mini_status")
    sim = eid("sim_status")
    dry = eid("dry_run_status")
    accuracy = eid("accuracy_status")

    header = (
        "## ESTADI | ENERGY PILOT\n"
        "**Pulpit doradczy — automatyczne sterowanie Deye WYŁĄCZONE.**\n\n"
        "Stan: **{{ states(" + _quote(status) + ") }}**\n\n"
        "Moc przyłącza: **{{ states(" + _quote(eid("grid_import")) + ") }} kW** "
        "· dostępny zapas: **{{ states(" + _quote(eid("grid_headroom")) + ") }} kW**\n\n"
        "Taryfa: **{{ states(" + _quote(eid("tariff")) + ") }}** "
        "· strefa: **{{ states(" + _quote(eid("tariff_zone")) + ") }}**\n\n"
        "Prognoza jest symulacją bez dodatkowego ładowania z sieci; "
        "przyszłe sesje EV pozostają nieznane."
    )

    forecasts = (
        "{% set points = state_attr(" + _quote(sim) + ", 'harmonogram_48h') or [] %}\n"
        "{% if points | count > 0 %}\n"
        "Dostępne godziny: **{{ states(" + _quote(eid("sim_hours")) + ") }} h** "
        "· jakość: **{{ states(" + _quote(eid("sim_quality")) + ") }}**\n\n"
        "| Czas | SOC końcowy | PV kWh | Dom kWh | Import kWh |\n"
        "|:--|--:|--:|--:|--:|\n"
        "{% for point in points %}\n"
        "{% if loop.index0 % 4 == 0 %}\n"
        "| {{ point.czas[5:16] }} | {{ point.soc_do }}% | "
        "{{ point.pv }} | {{ point.dom }} | {{ point.import }} |\n"
        "{% endif %}\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "Brak kompletnej osi prognozy 48h. Sprawdź sensor symulacji i Forecast.Solar.\n"
        "{% endif %}\n\n"
        "*Tabela pokazuje co czwartą godzinę. Pełna oś 48h jest dostępna "
        "w atrybucie `harmonogram_48h` sensora Symulacja 48h.*"
    )

    if dry:
        dry_text = (
            "Stan testu: **{{ states(" + _quote(dry) + ") }}** "
            "· decyzja: **{{ states(" + _quote(eid("dry_run_action")) + ") }}**\n\n"
            "Hipotetyczna moc: **{{ states(" + _quote(eid("dry_run_power")) + ") }} kW** "
            "· kompletne dni: **{{ states(" + _quote(eid("dry_run_days")) + ") }}/7**\n\n"
            "{% set events = state_attr(" + _quote(dry) + ", 'ostatnie_20_decyzji') or [] %}\n"
            "{% if events | count > 0 %}\n"
            "| Kiedy | Decyzja | Moc kW | Powód |\n"
            "|:--|:--|--:|:--|\n"
            "{% for event in events[:8] %}\n"
            "| {{ event.at[5:16] }} | {{ event.hipotetyczna_akcja or event.code }} "
            "| {{ event.suggested_kw }} | {{ event.why[:65] }} |\n"
            "{% endfor %}\n"
            "{% else %}Brak zebranych decyzji. {% endif %}\n\n"
            "*Żadne z tych poleceń nie zostało wysłane do Deye.*"
        )
    else:
        dry_text = "Dziennik dry-run jeszcze nie jest dostępny."

    if accuracy:
        accuracy_text = (
            "Stan pomiarów: **{{ states(" + _quote(accuracy) + ") }}**\n\n"
            "{% set pv = state_attr(" + _quote(accuracy) + ", 'skutecznosc_pv') or {} %}\n"
            "{% set soc = state_attr(" + _quote(accuracy) + ", 'porownania_soc') or {} %}\n"
            "Porównane dni PV: **{{ pv.get('dni', 0) }}** "
            "· błąd WAPE: **{{ pv.get('wape_pct', 'brak danych') }}%**\n\n"
            "| Horyzont SOC | Śr. błąd | Liczba porównań |\n"
            "|:--|--:|--:|\n"
            "{% for hours in ['3','6','12','24'] %}\n"
            "{% set row = soc.get(hours, {}) %}\n"
            "| {{ hours }}h | {{ row.get('mae_soc_pp', '—') }} p.p. "
            "| {{ row.get('porownania', 0) }} |\n"
            "{% endfor %}\n\n"
            "*Różnica SOC porównuje symulację bez dodatkowego ładowania z sieci "
            "z rzeczywistością; nie jest pomiarem oszczędności.*"
        )
    else:
        accuracy_text = "Brak encji weryfikacji prognoz."

    economy_id = eid("economic_status")
    economics_markdown = (
        "**Uwaga: to porównanie scenariuszy, nie rzeczywiste oszczędności.**\n\n"
        "Status: **{{ states(" + _quote(economy_id) + ") }}**\n\n"
        "{% set before = state_attr(" + _quote(economy_id) + ", 'scenariusz_bez_ladowania') or {} %}\n"
        "{% set after = state_attr(" + _quote(economy_id) + ", 'scenariusz_z_planem') or {} %}\n"
        "{% set reason = state_attr(" + _quote(economy_id) + ", 'przyczyna') %}\n"
        "**Wynik:** {{ reason or 'Brak porównania' }}\n\n"
        "| Parametr po 48h | Bez ładowania z sieci | Plan doradczy |\n"
        "|:--|--:|--:|\n"
        "| Import kWh | {{ before.get('import_kwh', '—') }} | {{ after.get('import_kwh', '—') }} |\n"
        "| Koszt importu PLN | {{ before.get('import_cost_pln', '—') }} | {{ after.get('import_cost_pln', '—') }} |\n"
        "| Eksport kWh | {{ before.get('export_kwh', '—') }} | {{ after.get('export_kwh', '—') }} |\n"
        "| Energia do magazynu z sieci kWh | {{ before.get('grid_battery_kwh', '—') }} "
        "| {{ after.get('grid_battery_kwh', '—') }} |\n"
        "| Końcowy SOC | {{ before.get('soc_end_pct', '—') }}% | {{ after.get('soc_end_pct', '—') }}% |\n\n"
        "*Nie dodawaj samodzielnie wartości końcowego SOC do rachunku w PLN. "
        "Dla net-billingu liczy się rzeczywisty system rozliczeń i wartości depozytu. "
        "Gdy końcowy SOC jest różny, wynik pieniężny nie jest porównywalną oszczędnością.*"
    ) if economy_id else "Brak encji Opłacalność — status; sprawdź wersję i integrację."

    ev_risk_text = (
        "**To wariant stresowy na podstawie historii, NIE przewidywany "
        "harmonogram samochodu.**\n\n"
        "{% set risk = state_attr(" + _quote(economy_id) +
        ", 'historyczny_wariant_ryzyka_EV') or {} %}\n"
        "{% set base = risk.get('baseline') or {} %}\n"
        "{% set plan = risk.get('plan') or {} %}\n"
        "Status: **{{ risk.get('status', 'Brak dostatecznej historii EV') }}**\n\n"
        "| Parametr | Bez ładowania magazynu | Plan magazynu |\n"
        "|:--|--:|--:|\n"
        "| EV (kWh) | {{ base.get('ev_kwh', '—') }} | {{ plan.get('ev_kwh', '—') }} |\n"
        "| Import (kWh) | {{ base.get('import_kwh', '—') }} | {{ plan.get('import_kwh', '—') }} |\n"
        "| Koszt importu (PLN) | {{ base.get('import_cost_pln', '—') }} "
        "| {{ plan.get('import_cost_pln', '—') }} |\n"
        "| SOC końcowy | {{ base.get('soc_end_pct', '—') }}% "
        "| {{ plan.get('soc_end_pct', '—') }}% |\n\n"
        "*Wiele historycznych godzin P90 może łączyć różne sesje EV. "
        "Nie traktuj tego jako prawdopodobieństwa, gwarancji ani gotowego sterowania.*"
    ) if economy_id else "Nie znaleziono sensora analizy ekonomicznej."
    calib_id = eid("calibration_status")
    calibration_text = (
        "**Ocena danych przed dniem testu:** "
        "najpierw uczymy się na starszych dniach, potem sprawdzamy kolejne.\n\n"
        "{% set load = state_attr(" + _quote(calib_id) + ", 'profil_domu_analiza_wsteczna') or {} %}\n"
        "{% set pv = state_attr(" + _quote(calib_id) + ", 'korekta_pv_rekomendacja') or {} %}\n"
        "{% set ev = state_attr(" + _quote(calib_id) + ", 'ev_historyczny_scenariusz_stresowy') or {} %}\n"
        "**Dom:** {{ load.get('tested_hours', 0) }} godzin testowanych "
        "· MAE {{ load.get('mae_kwh_hour', '—') }} kWh/h "
        "· WAPE {{ load.get('wape_pct', '—') }}%\n\n"
        "**PV:** {{ pv.get('complete_pv_days', 0) }} pełnych dni "
        "· sugerowana całkowita korekta {{ pv.get('suggested_total_pv_discount_pct', '—') }}%\n\n"
        "**EV:** {{ ev.get('complete_days', 0) }} pełnych dni "
        "· stan: {{ ev.get('status', 'brak') }}\n\n"
        "*Żadna korekta nie jest stosowana automatycznie. "
        "Deye Load obejmuje auto i pompę, więc odejmujemy je z bazy domu.*"
    ) if calib_id else "Nie znaleziono sensora kalibracji."
    pump_id = eid("pump_learn_status")
    pump_text = (
        "**Model pompy — tylko podgląd, NIE sterowanie.**\n\n"
        "Stan: **{{ states(" + _quote(pump_id) + ") }}**\n\n"
        "{% set model = state_attr(" + _quote(pump_id) + ", 'model_wyuczony_w_zakresach') or {} %}\n"
        "{% set quality = state_attr(" + _quote(pump_id) + ", 'jakosc') or 'wstępny' %}\n"
        "{% set preview = state_attr(" + _quote(pump_id) + ", 'porownanie_48h') or {} %}\n"
        "**Ocena historyczna:** {{ quality }} · "
        "{{ states(" + _quote(eid("pump_learn_days")) + ") }} pełnych dni · "
        "{{ states(" + _quote(eid("pump_learn_hours")) + ") }} godzin pomiarów.\n\n"
        "| Zakres temperatur | Moc typowa (W) | P90 (W) | Godziny |\n"
        "|:--|--:|--:|--:|\n"
        "{% for key, row in model.items() %}\n"
        "| {{ row.get('temperatura_min_c') }}…{{ row.get('temperatura_max_c') }}°C "
        "| {{ row.get('srednia_moc_p50_w') }} "
        "| {{ row.get('srednia_moc_p90_w') }} "
        "| {{ row.get('godziny') }} |\n"
        "{% endfor %}\n\n"
        "**Porównanie prognoz tylko dla godzin ze znaną pogodą i wyuczonym zakresem:**\n\n"
        "| Wyuczony model | Dotychczasowy model | Rozbieżność |\n"
        "|--:|--:|--:|\n"
        "| {{ preview.get('prognoza_nauczona_kwh', '—') }} kWh "
        "| {{ preview.get('prognoza_dotychczasowa_kwh', '—') }} kWh "
        "| {{ preview.get('roznica_kwh', '—') }} kWh |\n\n"
        "Obserwowane godziny prognozy: "
        "**{{ preview.get('porownywalne_godziny', 0) }} / 48**.\n\n"
        "*Deye Load zawiera pompę i EV. Brak temperatury albo mocy pompy nie jest zerem. "
        "Do oceny COP potrzeba dodatkowych pomiarów ciepła, których tutaj nie ma.*"
    ) if pump_id else "Brak sensora stanu uczenia pompy; zaktualizuj integrację."
    cards = [
        _markdown("Centrum sterowania — podgląd", header),
        _tiles("Stan instalacji", _existing(
            {**entities, **sources}, [
                ("SOC magazynu", "source_soc"), ("Produkcja PV", "source_pv"),
                ("Cały dom — Deye Load", "source_home"),
                ("Samochód EV", "source_ev"),
                ("Pompa ciepła", "source_pump"), ("Import sieci", "grid_import"),
            ]), 3),
        _tiles("Planowanie i bezpieczeństwo", _existing(
            entities, [("Stan systemu", "health_status"),
                       ("Grid Guard", "grid_status"),
                       ("Kontrola faz", "grid_phase_status"),
                       ("Docelowy SOC", "smart_charge_target"),
                       ("Proponowana moc", "smart_charge_power"),
                       ("Tryb testowy", "dry_run_status")]), 3),
        _entities("Najbliższe tanie okno", _existing(
            entities, [("Taryfa", "tariff"), ("Strefa", "tariff_zone"),
                       ("Cena brutto", "tariff_price"),
                       ("Początek taniej taryfy", "next_cheap"),
                       ("Start ładowania", "smart_charge_start"),
                       ("Przewidywany koniec", "smart_charge_finish"),
                       ("Energia z sieci", "smart_charge_energy"),
                       ("Powód decyzji", "grid_reason") ])),
        _graph("Zużycie i produkcja — ostatnie 24h",
               [sources[k] for k in ("source_pv", "source_home",
                                      "source_pump", "source_ev")
                if sources.get(k)]),
        _graph("Magazyn — SOC ostatnie 24h",
               [sources["source_soc"]] if sources.get("source_soc") else []),
        _graph("Import i zapas przyłącza — ostatnie 24h",
               [eid(k) for k in ("grid_import", "grid_headroom", "grid_charge_cap")
                if eid(k)]),
        _tiles("Symulacja magazynu 48h", _existing(
            entities, [("SOC na koniec", "sim_soc_end"),
                       ("Minimalny SOC", "sim_soc_min"),
                       ("Wariant ostrożny", "sim_soc_min_cautious"),
                       ("Produkcja PV", "sim_pv_kwh"),
                       ("Import energii", "sim_grid_kwh"),
                       ("Szczyt poboru", "sim_grid_peak")]), 3),
        _interactive_forecast_card(sim),
        _markdown("Prognoza — następne 48 godzin (zapasowa tabela 4h)", forecasts),
        _tiles("Ekonomia pracy magazynu — porównanie 48h", _existing(
            entities, [("Stan porównania", "economic_status"),
                       ("Import bez ładowania (PLN)", "economic_base_cost"),
                       ("Import z planem (PLN)", "economic_plan_cost"),
                       ("Różnica kosztu importu (PLN)", "economic_import_delta"),
                       ("Końcowy SOC bez planu", "economic_base_soc"),
                       ("Końcowy SOC z planem", "economic_plan_soc")]), 3),
        _markdown("Rachunek dwóch scenariuszy 48h", economics_markdown),
        _tiles("Kalibracja prognoz i niepewność EV", _existing(
            entities, [("Stan profilu domu", "calibration_status"),
                       ("Błąd profilu", "calibration_load_mae"),
                       ("WAPE domu", "calibration_load_wape"),
                       ("Sugerowana korekta PV", "calibration_pv_discount"),
                       ("Historyczne ryzyko EV", "calibration_ev_status"),
                       ("Kompletne dni EV", "calibration_ev_days")]), 3),
        _markdown("Jak uczymy się z rzeczywistych pomiarów", calibration_text),
        _tiles("Pompa ciepła — uczenie z temperatury", _existing(
            entities, [("Stan uczenia", "pump_learn_status"),
                       ("Dni pomiarów", "pump_learn_days"),
                       ("Godziny sparowane", "pump_learn_hours"),
                       ("Błąd na późniejszych dniach", "pump_learn_mae"),
                       ("Nowa prognoza pompy (kWh)", "pump_preview_learned"),
                       ("Dotychczasowa prognoza (kWh)", "pump_preview_legacy")]), 3),
        _markdown("Temperatura a zużycie pompy — model empiryczny", pump_text),
        _markdown("Co jeśli auto znowu będzie się ładować?", ev_risk_text),
        _markdown("Dry-run — decyzje i wyjaśnienia", dry_text),
        _markdown("Jak trafnie przewidujemy?", accuracy_text),
        _entities("Diagnostyka i stan Deye", _existing(
            entities, [("Rozpoznanie TOU", "deye_tou_status"),
                       ("Odczytane pola", "deye_tou_fields"),
                       ("Migawka ustawień", "deye_tou_snapshot"),
                       ("Gotowość automatyki", "deye_tou_ready"),
                       ("Wersja integracji", "version") ])),
    ]
    if entities.get("refresh"):
        cards.append(
            "- type: button\n"
            "  entity: " + _quote(entities["refresh"]) + "\n"
            "  name: \"Odśwież prognozę teraz\"\n"
            "  icon: mdi:refresh\n"
            "  show_state: false\n"
        )
    cards.append(_markdown(
        "Granice systemu",
        "**Tryb wyłącznie doradczy.** Grid Guard co 15 sekund nie zastępuje "
        "fizycznych zabezpieczeń przyłącza ani limitów BMS. Model nie steruje "
        "jeszcze Deye ani ładowarką EV; nie obliczamy rzeczywistych oszczędności "
        "bez potwierdzonych przepływów import/eksport i cen rozliczenia."
    ))
    return (
        "# ESTADI Energy Pilot — pulpit z lokalną kartą 48h (zarejestruj zasób JS w HA)\n"
        "title: \"ESTADI Energy Pilot\"\n"
        "views:\n"
        "  - title: \"Energia\"\n"
        "    path: estadi-energia\n"
        "    icon: mdi:solar-power\n"
        "    cards:\n"
        + "".join(_card(card) for card in cards)
    )


def _interactive_forecast_card(entity_id: str) -> str:
    """Local read-only JS card; user registers resource in Home Assistant."""
    return ("- type: custom:estadi-energy-forecast-card\n"
            + "  entity: " + _quote(entity_id) + "\n"
            + "  title: " + _quote("Prognoza 48h • SOC, PV, dom, EV, pompa i sieć") + "\n"
            + "  default_series:\n"
            + "    - soc\n"
            + "    - pv\n"
            + "    - dom\n"
            + "    - import\n"
            + "    - pompa\n"
            + "    - auto\n")


def render_mini_widget(entities: Mapping[str, str], sources: Mapping[str, str]) -> str:
    """Render compact list of cards for a new HA dashboard view."""
    status = entities.get("mini_status")
    if not status:
        raise ValueError("Brak sensora Szybki status energii")
    soc = sources.get("source_soc")
    content = (
        "## ⚡ ESTADI Energy Pilot\n"
        "{{ states(" + _quote(status) + ") }}\n\n"
        "**Tryb:** doradczy · sterowanie Deye wyłączone\n\n"
        "**Decyzja testowa:** {{ states(" + _quote(entities.get("dry_run_action", "")) + ") }}\n"
        "{% set decision = state_attr(" + _quote(entities.get("dry_run_status", "")) + ", 'hipotetyczna_decyzja') or {} %}\n"
        "**Powód:** {{ decision.get('why', 'Brak danych') }}"
    )
    mini = [
        _markdown("Status", content),
        _tiles("Teraz", _existing(
            {**sources, **entities},
            [("SOC", "source_soc"), ("Import", "grid_import"),
             ("PV", "source_pv"), ("Auto", "source_ev")]), 2),
        _entities("Najbliższy plan", _existing(
            entities, [("Początek", "smart_charge_start"),
                       ("Docelowy SOC", "smart_charge_target"),
                       ("Proponowana moc", "smart_charge_power"),
                       ("Grid Guard", "grid_status") ])),
    ]
    return ("# ESTADI Energy Pilot — miniwidżet\n"
            "title: \"ESTADI — mini\"\n"
            "views:\n"
            "  - title: \"Szybki status\"\n"
            "    path: estadi-mini\n"
            "    icon: mdi:battery-charging\n"
            "    cards:\n"
            + "".join(_card(card) for card in mini))


def export_files(directory: str | Path, full: str, mini: str,
                 javascript: str | None = None) -> dict[str, str]:
    """Safely create YAMLs with no overwrite of the owner's existing edits.

    This is triggered only by the explicit 'Eksportuj panel' HA button.
    The files contain no secret credentials, only entity IDs and Lovelace YAML.
    """
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("Brak katalogu konfiguracji Home Assistant")
    if not full.strip() or not mini.strip():
        raise ValueError("Pusta konfiguracja pulpitu")
    targets = {}
    if javascript is not None:
        if not javascript.strip() or "estadi-energy-forecast-card" not in javascript:
            raise ValueError("Nieprawidłowy kod karty prognozy 48h")
        www = root / "www"
        www.mkdir(exist_ok=True)
        resource = www / FORECAST_CARD_JS
        # Never overwrite user edits; versioned name avoids stale browser cache.
        try:
            with resource.open("x", encoding="utf-8") as file:
                file.write(javascript)
        except FileExistsError:
            if resource.read_text(encoding="utf-8") != javascript:
                raise ValueError(
                    "Istnieje zmodyfikowany zasób karty. Nie nadpisano: " + str(resource)
                )
        targets["forecast_js"] = str(resource)
        targets["forecast_resource_url"] = FORECAST_CARD_RESOURCE
    for key, filename, text in (
        ("dashboard", "estadi-energy-pilot-dashboard.yaml", full),
        ("mini", "estadi-energy-pilot-mini.yaml", mini),
    ):
        # Never overwrite a customized dashboard. Subsequent exports get -2...
        for version in range(1, 1000):
            suffix = "" if version == 1 else f"-{version}"
            candidate = root / filename.replace(".yaml", f"{suffix}.yaml")
            try:
                with candidate.open("x", encoding="utf-8") as output:
                    output.write(text)
            except FileExistsError:
                continue
            targets[key] = str(candidate)
            break
        else:
            raise RuntimeError("Zbyt wiele istniejących eksportów")
    return targets
