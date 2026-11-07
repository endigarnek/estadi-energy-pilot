"""Offline-rendered native Home Assistant Lovelace dashboards.

The export is deliberately a *user-initiated* operation. It creates two YAML
files in /config using actual Entity Registry IDs; does not create/overwrite
a Lovelace dashboard, modify HA storage, or control Deye.
No frontend add-ons or external services are required.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from textwrap import indent
from typing import Mapping

FORECAST_CARD_JS = "estadi-energy-pilot-ui-v046.js"
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


def _metric_card(title: str, items: list[tuple[str, str]],
                 columns: int = 3) -> str:
    """One readable responsive ESTADI panel instead of many tiny HA tiles."""
    if not items:
        return _markdown(title, "Brak danych do wyświetlenia.")
    return (
        "- type: custom:estadi-energy-details-card\n"
        "  title: " + _quote(title) + "\n"
        "  items:\n"
        + "".join("    - label: " + _quote(label) + "\n"
                  "      entity: " + _quote(entity_id) + "\n"
                  for label, entity_id in items)
    )


def render_dashboard(entities: Mapping[str, str], sources: Mapping[str, str]) -> str:
    """Generate one complete native Lovelace dashboard, without guessed IDs."""
    # Charging status is optional: it is informative, not needed to render Lovelace.
    required = ("mini_status", "grid_status", "sim_status")
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
    excess_id = eid("pump_excess_status")
    pump_excess_text = (
        "**Diagnostyka wyłącznie z pomiarów historycznych — bez sterowania.**\n\n"
        "Stan: **{{ states(" + _quote(excess_id) + ") }}**.\n\n"
        "{% set row = state_attr(" + _quote(excess_id) + ", 'ostatnie_okresy') or [] %}\n"
        "Porównano **{{ states(" + _quote(eid("pump_excess_hours")) + ") }} godzin** "
        "z wcześniejszymi dniami o podobnej temperaturze.\n\n"
        "Wykryte okresy: **{{ states(" + _quote(eid("pump_excess_events")) + ") }}** "
        "· oszacowana nadwyżka: **{{ states(" + _quote(eid("pump_excess_kwh")) + ") }} kWh**.\n\n"
        "| Początek | Godzin | Zużycie | Nadwyżka |\n"
        "|:--|--:|--:|--:|\n"
        "{% for ev in row[-10:] %}\n"
        "| {{ ev.get('start', '—') }} | {{ ev.get('hours', '—') }} "
        "| {{ ev.get('actual_kwh', '—') }} kWh "
        "| {{ ev.get('estimated_excess_kwh', '—') }} kWh |\n"
        "{% endfor %}\n\n"
        "*Przyczyna pozostaje nieustalona. Podwyższony pobór może towarzyszyć "
        "CWU, odszranianiu, grzałce lub innym trybom, ale nie jest dowodem żadnego z nich. "
        "Bez pomiarów stanu sprężarki/CWU nie liczymy cykli. "
        "Gdy brakuje historii, liczba zdarzeń pozostaje nieokreślona — nie jest zerem.*"
    ) if excess_id else "Brak sensora oceny nadwyżek pompy."
    cards = [
        _markdown("Centrum sterowania — podgląd", header),
        _metric_card("Stan instalacji", _existing(
            {**entities, **sources}, [
                ("SOC magazynu", "source_soc"), ("Produkcja PV", "source_pv"),
                ("Cały dom — Deye Load", "source_home"),
                ("Samochód EV", "source_ev"),
                ("Pompa ciepła", "source_pump"), ("Import sieci — zweryfikowany", "grid_import"),
                ("Deye — odczyt mocy ze znakiem (nie import!)", "grid_raw_power"),
            ]), 3),
        _metric_card("Planowanie i bezpieczeństwo", _existing(
            entities, [("Stan systemu", "health_status"),
                       ("Grid Guard", "grid_status"),
                       ("Odczyt czujnika Deye", "grid_raw_status"),
                       ("Inteligentne ładowanie", "smart_charge_status"),
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
        _graph("Produkcja i zużycie — ostatnie 48h",
               [sources[k] for k in ("source_pv", "source_home",
                                      "source_pump", "source_ev")
                if sources.get(k)], hours=48),
        _graph("Magazyn — SOC ostatnie 48h",
               [sources["source_soc"]] if sources.get("source_soc") else [], hours=48),
        _graph("Import i zapas przyłącza — ostatnie 48h",
               [eid(k) for k in ("grid_import", "grid_raw_power", "grid_headroom", "grid_charge_cap")
                if eid(k)], hours=48),
        _metric_card("Symulacja magazynu 48h", _existing(
            entities, [("SOC na koniec", "sim_soc_end"),
                       ("Minimalny SOC", "sim_soc_min"),
                       ("Wariant ostrożny", "sim_soc_min_cautious"),
                       ("Produkcja PV", "sim_pv_kwh"),
                       ("Import energii", "sim_grid_kwh"),
                       ("Szczyt poboru", "sim_grid_peak")]), 3),
        _interactive_forecast_card(sim),
        _markdown("Prognoza — następne 48 godzin (zapasowa tabela 4h)", forecasts),
        _metric_card("Ekonomia pracy magazynu — porównanie 48h", _existing(
            entities, [("Stan porównania", "economic_status"),
                       ("Import bez ładowania (PLN)", "economic_base_cost"),
                       ("Import z planem (PLN)", "economic_plan_cost"),
                       ("Różnica kosztu importu (PLN)", "economic_import_delta"),
                       ("Końcowy SOC bez planu", "economic_base_soc"),
                       ("Końcowy SOC z planem", "economic_plan_soc")]), 3),
        _markdown("Rachunek dwóch scenariuszy 48h", economics_markdown),
        _metric_card("Kalibracja prognoz i niepewność EV", _existing(
            entities, [("Stan profilu domu", "calibration_status"),
                       ("Błąd profilu", "calibration_load_mae"),
                       ("WAPE domu", "calibration_load_wape"),
                       ("Sugerowana korekta PV", "calibration_pv_discount"),
                       ("Historyczne ryzyko EV", "calibration_ev_status"),
                       ("Kompletne dni EV", "calibration_ev_days")]), 3),
        _markdown("Jak uczymy się z rzeczywistych pomiarów", calibration_text),
        _metric_card("Pompa ciepła — uczenie z temperatury", _existing(
            entities, [("Stan uczenia", "pump_learn_status"),
                       ("Dni pomiarów", "pump_learn_days"),
                       ("Godziny sparowane", "pump_learn_hours"),
                       ("Błąd na późniejszych dniach", "pump_learn_mae"),
                       ("Nowa prognoza pompy (kWh)", "pump_preview_learned"),
                       ("Dotychczasowa prognoza (kWh)", "pump_preview_legacy")]), 3),
        _markdown("Temperatura a zużycie pompy — model empiryczny", pump_text),
        _metric_card("Pompa — kontrola podwyższonego poboru", _existing(
            entities, [("Stan analizy", "pump_excess_status"),
                       ("Porównane godziny", "pump_excess_hours"),
                       ("Podejrzane okresy", "pump_excess_events"),
                       ("Nadwyżka poboru", "pump_excess_kwh"),
                       ("Ostatni okres", "pump_excess_last")]), 3),
        _markdown("Pompa — historyczne okresy zwiększonego poboru", pump_excess_text),
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
    def view(title: str, path: str, icon: str,
             groups: list[tuple[str, str, list[str]]],
             panel: bool = False) -> str:
        """Use the native HA Sections layout for clear two-column alignment."""
        header = (
            "  - title: " + _quote(title) + "\n"
            "    path: " + path + "\n"
            "    icon: " + icon + "\n"
        )
        if panel:
            return (header + "    type: panel\n    cards:\n"
                    + "".join(_card(card) for _, _, items in groups for card in items))
        result = header + "    type: sections\n    max_columns: 2\n    sections:\n"
        for heading, heading_icon, selected in groups:
            if not selected:
                continue
            result += (
                "      - type: grid\n"
                "        cards:\n"
                "          - type: heading\n"
                "            heading: " + _quote(heading) + "\n"
                "            icon: " + heading_icon + "\n"
            )
            for card in selected:
                result += indent(card.rstrip(), "          ") + "\n"
        return result

    def test_button(key: str, title: str) -> str:
        eid = entities.get("lab_" + key)
        if not eid:
            return ""
        return (
            "- type: button\n"
            "  entity: " + _quote(eid) + "\n"
            "  name: " + _quote(title) + "\n"
            "  icon: mdi:flask-outline\n"
            "  show_state: false\n"
            "  tap_action:\n"
            "    action: perform-action\n"
            "    perform_action: button.press\n"
            "    target:\n"
            "      entity_id: " + _quote(eid) + "\n"
        )

    lab_buttons = [
        test_button("meters", "Sprawdź pomiar Deye"),
        test_button("polarity", "Sprawdź kierunki mocy"),
        test_button("limits", "Sprawdź limity i fazy"),
        test_button("forecast", "Sprawdź prognozę 48h"),
        test_button("tou", "Sprawdź Deye TOU"),
        test_button("write_capability", "Sprawdź możliwość regulacji"),
        test_button("preflight", "Sprawdź gotowość sterowania"),
    ]
    lab_buttons = [card for card in lab_buttons if card]
    lab_result = entities.get("lab_status")
    lab_info = [_markdown("Laboratorium Deye",
        "**Wszystkie przyciski są testami tylko do odczytu.** "
        "Nie wysyłają komend, nie zmieniają mocy ładowania i nie zapisują "
        "ustawień falownika. Test możliwości regulacji wykrywa wyłącznie "
        "potencjalne encje number, select lub switch. "
        "**Rzeczywisty test zmiany mocy wymaga potwierdzenia modelu, "
        "semantyki komendy, odczytu zwrotnego i sposobu przywrócenia ustawień.**")]
    if lab_result:
        lab_info.append("- type: entities\n"
                        "  title: \"Wynik ostatniego testu — dotknij po szczegóły\"\n"
                        "  entities:\n"
                        "    - entity: " + _quote(lab_result) + "\n")
    full_plan = (
        "- type: custom:estadi-energy-plan-card\n"
        "  entity: " + _quote(entities["plan_timeline"]) + "\n"
    ) if entities.get("plan_timeline") else _markdown(
        "Plan dobowy", "Brakuje encji harmonogramu 48h — odśwież integrację.")

    overview = _control_cockpit_card(entities, sources)
    return (
        "# ESTADI Energy Pilot — zarządzany pulpit, v0.5.0\n"
        "title: \"ESTADI Energy Pilot\"\n"
        "views:\n"
        + view("Pulpit", "estadi-energia", "mdi:view-dashboard",
               [("", "", [overview])], panel=True)
        + view("Historia", "estadi-historia", "mdi:chart-line", [
            ("Bilans domu", "mdi:home-lightning-bolt",
             [cards[4]]),
            ("Magazyn energii", "mdi:battery",
             [cards[5]]),
            ("Przyłącze", "mdi:transmission-tower",
             [cards[6]]),
            ("Aktualne pomiary", "mdi:gauge",
             [cards[1]]),
        ])
        + view("Prognoza 48h", "estadi-prognoza", "mdi:chart-timeline-variant", [
            ("Rzeczywisty plan magazynu (tylko symulacja)", "mdi:battery-clock",
             [full_plan]),
            ("Prognoza godzinowa", "mdi:chart-bell-curve-cumulative",
             [cards[8]]),
            ("Scenariusz 48 godzin", "mdi:calendar-clock",
             [cards[7], cards[9]]),
            ("Jakość źródła prognozy PV", "mdi:weather-sunny-alert",
             [_metric_card("Pokrycie prognozy PV", _existing(
                 entities, [("Pokrycie słonecznych godzin", "pv_coverage"),
                            ("Dostępne godziny symulacji", "sim_hours"),
                            ("Status symulacji", "sim_status")]))]),
            ("Kolejne tanie okno", "mdi:clock-outline",
             [cards[3]]),
        ])
        + view("Koszty", "estadi-koszty", "mdi:cash-multiple", [
            ("Porównanie scenariuszy", "mdi:finance",
             [cards[10], cards[11]]),
            ("Niepewność ładowania EV", "mdi:car-electric",
             [cards[18]]),
        ])
        + view("Testy", "estadi-testy", "mdi:flask-outline", [
            ("Diagnostyka bez sterowania", "mdi:shield-check",
             lab_info),
            ("Uruchom test", "mdi:flask-outline",
             lab_buttons),
        ])
        + view("Diagnostyka", "estadi-diagnostyka", "mdi:stethoscope", [
            ("Stan bezpieczeństwa", "mdi:shield-check-outline",
             [cards[0], cards[2]]),
            ("Kalibracja odczytów", "mdi:tune-variant",
             [cards[12], cards[13]]),
            ("Model pompy ciepła", "mdi:heat-pump-outline",
             [cards[14], cards[15]]),
            ("Nietypowe zużycie pompy", "mdi:chart-bell-curve",
             [cards[16], cards[17]]),
            ("Symulacje i trafność", "mdi:clipboard-pulse",
             [cards[19], cards[20]]),
            ("Integracja Deye", "mdi:solar-power-variant",
             cards[21:]),
        ])
    )


def _control_cockpit_card(entities: Mapping[str, str], sources: Mapping[str, str]) -> str:
    """Compact home screen: current power flow, plan, reliable 48h and actuals."""
    mapping = {
        "soc": sources.get("source_soc"),
        "pv": sources.get("source_pv"),
        "home": sources.get("source_home"),
        "ev": sources.get("source_ev"),
        "pump": sources.get("source_pump"),
        "battery_power": sources.get("source_battery"),
        "battery_state": sources.get("source_battery_state"),
        "losses": sources.get("source_losses"),
        "grid_import": entities.get("grid_import"),
        "grid_raw": entities.get("grid_raw_power"),
        "grid_limit": entities.get("grid_limit"),
        "grid_headroom": entities.get("grid_headroom"),
        "grid_status": entities.get("grid_status"),
        "smart_charge_status": entities.get("smart_charge_status"),
        "smart_charge_power": entities.get("smart_charge_power"),
        "smart_charge_start": entities.get("smart_charge_start"),
        "smart_charge_finish": entities.get("smart_charge_finish"),
        "smart_charge_target": entities.get("smart_charge_target"),
        "smart_charge_energy": entities.get("smart_charge_energy"),
        "sim_status": entities.get("sim_status"),
        "sim_hours": entities.get("sim_hours"),
        "sim_pv_kwh": entities.get("sim_pv_kwh"),
        "sim_grid_kwh": entities.get("sim_grid_kwh"),
        "sim_soc_end": entities.get("sim_soc_end"),
        "next_cheap": entities.get("next_cheap"),
        "history_status": entities.get("history_status"),
        "plan_timeline": entities.get("plan_timeline"),
    }
    return ("- type: custom:estadi-energy-control-card\n" +
            "".join("  entity_" + key + ": " + _quote(eid) + "\n"
                    for key, eid in mapping.items() if eid))


def _modern_overview_card(entities: Mapping[str, str], sources: Mapping[str, str]) -> str:
    mapping = {
        "soc": sources.get("source_soc"),
        "pv": sources.get("source_pv"),
        "home": sources.get("source_home"),
        "ev": sources.get("source_ev"),
        "pump": sources.get("source_pump"),
        "grid_import": entities.get("grid_import"),
        "grid_limit": entities.get("grid_limit"),
        "grid_headroom": entities.get("grid_headroom"),
        "grid_status": entities.get("grid_status"),
        "health_status": entities.get("health_status"),
        "tariff_zone": entities.get("tariff_zone"),
        "next_cheap": entities.get("next_cheap"),
        "smart_charge_power": entities.get("smart_charge_power"),
        "smart_charge_target": entities.get("smart_charge_target"),
    }
    return ("- type: custom:estadi-energy-overview-card\n" +
            "".join("  entity_" + key + ": " + _quote(eid) + "\n"
                    for key, eid in mapping.items() if eid))


def _interactive_forecast_card(entity_id: str) -> str:
    """Local read-only JS card; user registers resource in Home Assistant."""
    return ("- type: custom:estadi-energy-forecast-card\n"
            + "  entity: " + _quote(entity_id) + "\n"
            + "  title: " + _quote("Prognoza 48h • SOC, PV, dom, EV, pompa i sieć") + "\n"
            + "  default_series:\n"
            + "    - soc\n"
            + "    - pv\n"
            + "    - import\n"
            + "    - auto\n")


def render_mini_widget(entities: Mapping[str, str], sources: Mapping[str, str]) -> str:
    """Compact, responsive and live card — no tiny legacy tile layout."""
    if not entities.get("mini_status"):
        raise ValueError("Brak sensora Szybki status energii")
    card = _modern_overview_card(entities, sources) + "  mode: compact\n"
    return (
        "# ESTADI — miniwidżet do osobnego widoku lub skopiowania jako karta\n"
        "title: \"ESTADI — mini\"\n"
        "views:\n"
        "  - title: \"Szybki status\"\n"
        "    path: estadi-mini\n"
        "    icon: mdi:battery-charging\n"
        "    type: panel\n"
        "    cards:\n"
        + _card(card)
    )


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_atomic(path: Path, content: str) -> None:
    """Write only when changed; replace atomically on the same filesystem."""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".estadi-tmp-", delete=False
        ) as temp:
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
            temp_path = Path(temp.name)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def export_files(directory: str | Path, full: str, mini: str,
                 javascript: str | None = None) -> dict[str, str]:
    """Idempotent managed export; never creates -2, -3 or unbounded copies.

    Existing legacy exports and the user's manually edited dashboards are left
    untouched. A checksum manifest tracks only files created by this exporter.
    If one of those files is later edited by the owner, fail clearly instead
    of silently overwriting their work or allocating another numbered file.
    """
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("Brak katalogu konfiguracji Home Assistant")
    if not full.strip() or not mini.strip():
        raise ValueError("Pusta konfiguracja pulpitu")
    if javascript is not None and (
        not javascript.strip() or
        "estadi-energy-forecast-card" not in javascript or
        "estadi-energy-overview-card" not in javascript or
        "estadi-energy-control-card" not in javascript or
        "estadi-energy-details-card" not in javascript or
        "estadi-energy-plan-card" not in javascript
    ):
        raise ValueError("Nieprawidłowy kod kart ESTADI")

    files = {
        "dashboard": ("estadi-energy-pilot-dashboard-managed.yaml", full),
        "mini": ("estadi-energy-pilot-mini-managed.yaml", mini),
    }
    if javascript is not None:
        files["forecast_js"] = ("www/" + FORECAST_CARD_JS, javascript)
    manifest_path = root / ".estadi-energy-pilot-managed.json"
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(previous, dict):
                raise ValueError("Nieprawidłowy rejestr plików zarządzanych")
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Uszkodzony rejestr plików ESTADI") from exc
    else:
        previous = {}

    # Check every existing target before writing any files.
    for filename, content in files.values():
        target = root / filename
        if target.exists():
            actual = _digest(target.read_text(encoding="utf-8"))
            recorded = previous.get(filename)
            if recorded is None and actual != _digest(content):
                raise ValueError("Istnieje niezarządzany plik. Nie nadpisano: " + str(target))
            if recorded is not None and recorded != actual:
                raise ValueError("Plik zmieniono ręcznie. Nie nadpisano: " + str(target))

    targets: dict[str, str] = {}
    updated = dict(previous)
    for key, (filename, content) in files.items():
        target = root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(target, content)
        updated[filename] = _digest(content)
        targets[key] = str(target)
    if updated != previous:
        _write_atomic(manifest_path, json.dumps(updated, sort_keys=True, indent=2) + "\n")
    if javascript is not None:
        targets["forecast_resource_url"] = FORECAST_CARD_RESOURCE
    return targets
