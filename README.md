# ESTADI Energy Pilot — wersja 0.2.2

**Własna integracja Home Assistant (HACS) do prognozowania ładowania magazynu energii i oceny trafności prognoz.** Wersja **doradcza**: odczytuje sensory, oblicza cele SOC, ale **nie steruje falownikiem Deye**.

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



## Nowość 0.2.2 — krótki kreator, bez szukania encji

Po aktualizacji przez HACS **pobierz ponownie integrację i uruchom ponownie cały Home Assistant**. W razie widocznego starego opisu („Wersja 0.1”) zamknij kreator i wszystkie karty przeglądarki z Home Assistant, a następnie otwórz panel ponownie. Samo przeładowanie integracji lub aktualizacja metadanych HACS nie wystarczy.

Nowy kreator wyszukuje istniejące sensory, w tym cztery znane encje Deye/PV/dom/Shelly/EV. **Nie wyświetla wykrytych już czujników jako pól wyboru.** Prosi tylko o brakujące źródła Solcast, SOC i temperaturę zewnętrzną, plus dwie wartości: *rzeczywistą użyteczną pojemność magazynu* (bez automatycznego domyślnego 15 kWh) oraz średnią moc bazową domu (domyślnie 400 W; to założenie do weryfikacji).

W istniejącej konfiguracji menu **Konfiguruj** pokazuje prosty ekran (pojemność, moc bazowa, rezerwa i pole „Pokaż zaawansowane ustawienia”). Gdy zaznaczysz pole, przejdziesz do wszystkich encji i harmonogramu. Rozpoznane sensory zapisywane są przy pierwszym zatwierdzeniu kreatora, a w istniejącej konfiguracji są automatycznie wykorzystywane bez reinstalacji.

Jeżeli na formularzu pozostają puste pola Solcast, być może zainstalowana jest tylko integracja **Forecast.Solar**. To inne źródło danych niż **Solcast PV Forecast**; nie należy wybierać Forecast.Solar jako Solcast bez zaimplementowania adaptera.

## Wersja 0.2.1 — automatyczny wybór czujników

Po aktualizacji do **0.2.1** czujniki rozpoznawane są automatycznie, jeśli wciąż istnieją w Home Assistant i raportują właściwe jednostki:

| Pomiar | Automatycznie wybierana encja |
|---|---|
| Deye: produkcja PV (moc) | `sensor.deye_pv_power` |
| Deye: zużycie domu (moc) | `sensor.deye_load_power` |
| Pompa ciepła: moc elektryczna | `sensor.shellyem3_08f9e051e0b0_channel_b_power` |
| Ładowarka EV: rzeczywista moc | `sensor.moc_ladowarki_poprawna` |

W kreatorze oraz na stronie **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → Konfiguruj** moduł podpowiada również jednoznacznie rozpoznane encje **Solcast, SOC Deye i temperatury zewnętrznej**. Jeśli jest więcej pasujących encji albo brak poprawnej jednostki, pole zostaje puste — system niczego nie zgaduje. Wcześniej zapisane ręczne wybory mają pierwszeństwo.

**Nie usuwaj dotychczasowej integracji!** Po aktualizacji moduł zacznie korzystać ze znalezionych czterech czujników również w już istniejącej konfiguracji. Jeżeli chcesz przejrzeć lub zmienić źródła danych, wybierz **Konfiguruj** i zatwierdź. Pojemność użyteczną magazynu trzeba potwierdzić ręcznie — nie da się jej bezpiecznie wywnioskować z samych nazw sensorów. **Wersja nadal nie steruje Deye**.

## Nowość 0.2 — historia prognoz i ładowarki EV

Po aktualizacji wybierz **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → Konfiguruj** i wskaż cztery opcjonalne czujniki:

| Rola | Encja z Twojego Home Assistant |
|---|---|
| Moc paneli | `sensor.deye_pv_power` |
| Moc domu | `sensor.deye_load_power` |
| Moc pompy ciepła | `sensor.shellyem3_08f9e051e0b0_channel_b_power` |
| Moc ładowarki EV | `sensor.moc_ladowarki_poprawna` |

Wartości mocy są przyjmowane **wyłącznie** z czujników o jednostkach W lub kW, a wartości ujemne/nieprawidłowe są pomijane. Historia nie jest uzupełniana zmyślonymi zerami, jeśli HA był wyłączony lub sensor był niedostępny.

**Co zapisujemy** (bez dodatkowej bazy, w wewnętrznym magazynie Home Assistanta `.storage`):

- Około 21:00: **zamrożona prognoza Solcast na następny dzień**, ze szczegółami co godzinę, niepodmieniana w późniejszych aktualizacjach.
- Co 15 minut: zmierzone moce i oszacowana na ich podstawie energia PV, domu, pompy ciepła i ładowarki EV, z pokryciem danych dla każdej godziny.
- Do **45 dni** danych; w czujniku błędu prognozy atrybuty `ostatnie_dni` i `godziny_wczoraj`.
- Różnica prognoza/rzeczywistość liczona wyłącznie dla **zakończonych dni** z co najmniej 90% pokryciem pomiaru PV. W innym przypadku brak oceny, a nie fałszywy wynik.

Czujniki nowej wersji: `Wczorajsza prognoza PV (z 21:00)`, `Wczorajsza produkcja PV — pomiar`, `Błąd wczorajszej prognozy PV`, `Kompletność pomiaru PV wczoraj`, energia ładowarki EV i pompy ciepła (wczoraj), energia EV/PV (dziś).

**To szacunki energii z próbek mocy co 15 minut, a nie odczyty licznika rozliczeniowego.** Porównania prognoz zaczną być sensowne dopiero po zebraniu pełnej doby (z wieczorną prognozą z poprzedniego dnia). Ładowarka 11 kW pracująca przy 10 A ma realnie ok. 6,9 kW; moduł bierze **zmierzone** W, nie wpisaną moc maksymalną. Zużycie domu może już zawierać pompę i EV — **nie sumujemy** ich dodatkowo do domu.

Wersja jest dalej **tylko doradcza**: NIE zapisuje ustawień falownika Deye, NIE reguluje prądu ładowarki i NIE publikuje gotowego panelu Lovelace z wykresami. Zachowane dane godzinowe można wykorzystywać do budowy wykresu porównania w następnym etapie.

## Testy lokalne

```bash
python -m unittest discover -s tests -v
```

GitHub Actions uruchamia również testy przy nowych zmianach.

## Plan

- v0.2: gotowe dane historyczne i sensory. Kolejne: wygodny pulpit Lovelace z wykresem godzinowym.
- v0.3: nauka zużycia domu oraz korekta prognoz na podstawie pomiarów.
- v0.4: najpierw symulacja (dry-run), później opcjonalne sterowanie Deye po sprawdzeniu jego konkretnych encji i ograniczeń.

Zgłoszenia: [Issues](https://github.com/endigarnek/estadi-energy-pilot/issues).
