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
        _markdown("Prognoza — następne 48 godzin (krok 4h)", forecasts),
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
        "# ESTADI Energy Pilot — pulpit natywny, bez dodatkowych wtyczek\n"
        "title: \"ESTADI Energy Pilot\"\n"
        "views:\n"
        "  - title: \"Energia\"\n"
        "    path: estadi-energia\n"
        "    icon: mdi:solar-power\n"
        "    cards:\n"
        + "".join(_card(card) for card in cards)
    )


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
        "{% set decision = state_attr(" + _quote(entities.get("dry_run_status", "")) + ", 'hipotetyczna_decyzja') or {} %}\\n"
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


def export_files(directory: str | Path, full: str, mini: str) -> dict[str, str]:
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
