# ESTADI Energy Pilot v0.1.1

**Własna integracja Home Assistant (HACS) do prognozowania ładowania magazynu energii.** Wersja **doradcza**: odczytuje sensory, oblicza cele SOC, ale **nie steruje falownikiem Deye**.

## Instalacja przez HACS — bez kopiowania plików

1. W Home Assistant otwórz **HACS → Integracje**.
2. Otwórz menu (trzy kropki) i wybierz **Własne repozytoria / Custom repositories**.
3. Wklej adres: **https://github.com/endigarnek/estadi-energy-pilot**
4. Jako typ wybierz **Integracja / Integration** i zatwierdź.
5. Znajdź **ESTADI Energy Pilot**, kliknij **Pobierz / Download**, a następnie (jeżeli pojawi się taki komunikat) **uruchom ponownie Home Assistant**.
6. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację**, wyszukaj **ESTADI Energy Pilot**.
7. Wskaż sensory Solcast na dziś i jutro, stan baterii (%), temperaturę zewnętrzną, opcjonalnie prognozę pogody. Wprowadź **użyteczną** pojemność baterii (kWh) i średnią moc domu **bez pompy** (W).

HACS może pobierać zawartość domyślnej gałęzi repozytorium także bez wydania GitHub Release. Jeśli nie masz HACS, najpierw trzeba zainstalować sam HACS. Można również wgrać ręcznie folder `custom_components/estadi_energy_pilot` do `/config/custom_components/` i zrestartować HA.

## Co oblicza

- **Solcast**: szczegółowa półgodzinna (lub godzinowa) prognoza produkcji dla wybranych dni.
- **Pompa ciepła**: przy temperaturze od +8°C w górę przyjęte 0 W, tuż poniżej +8°C ok. 600 W, przy -5°C i niższych ok. 1200 W (wartości konfigurowalne). Są to **założenia**, a nie odczyty z licznika.
- Dwa osobne cele **SOC**: na koniec nocnej strefy taniej (domyślnie 07:00, energia do 13:00) oraz na koniec popołudniowej (16:00, energia do 21:00).
- Uwzględnia rezerwę SOC, margines 1 kWh, redukcję prognozy PV ze względu na ryzyko i przybliżoną sprawność energetyczną.
- Czujniki celu SOC, prognozy PV, zużycia oraz ilości kWh do doładowania w bieżącym tanim oknie. Odświeżanie co 15 minut.

**Ważne:** integracja nie ma jeszcze dopracowanego interfejsu z wykresem ani własnego automatycznego uczenia się. Jest to MVP do sprawdzenia obliczeń na Twojej instalacji, nie gotowy sterownik.

## Solcast — wymagane dane

Integracja jest przygotowana do współpracy z [BJReplay/ha-solcast-solar](https://github.com/BJReplay/ha-solcast-solar). W jej konfiguracji włącz szczegółowe atrybuty **detailedForecast** (lub **detailedHourly**) dziennych sensorów `Forecast Today` oraz `Forecast Tomorrow`. Jeżeli brak szczegółowych danych, nasza integracja zasygnalizuje brak prognozy i nie wyliczy celu SOC.

Dla każdej pozycji `pv_estimate` oznacza średnią **moc w kW** przez okres, a nie kWh.

## Konfiguracja i bezpieczeństwo

Ustawienia można później zmienić: **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → Konfiguruj**.

- Nie podłączaj automatycznego zapisu celu SOC do falownika na podstawie tego prototypu.
- Zweryfikuj wyliczenia na kilku dniach rzeczywistych danych przed rozważaniem sterowania.
- Sprawdź godziny tanich taryf w umowie i popraw parametry w integracji; ustawienia domyślne (21–07, 13–16) są przykładowe.
- Model nie obejmuje CWU, odmrażania, aut elektrycznych, indywidualnego harmonogramu pompy ani cen energii.
- Brak aktualnej prognozy lub pomiarów uniemożliwia wyliczenie zalecanego ładowania.

## Testy lokalne

```bash
python -m unittest discover -s tests -v
```

GitHub Actions uruchamia również testy przy nowych zmianach.

## Plan

- v0.2: gotowy pulpit z wykresem PV i prostym panelem konfiguracji.
- v0.3: nauka zużycia domu oraz korekta prognoz na podstawie pomiarów.
- v0.4: najpierw symulacja (dry-run), później opcjonalne sterowanie Deye po sprawdzeniu jego konkretnych encji i ograniczeń.

Zgłoszenia: [Issues](https://github.com/endigarnek/estadi-energy-pilot/issues).
