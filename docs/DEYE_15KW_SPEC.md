# ESTADI Energy Pilot — Deye 15 kW (LV), dane producenta i mapa sterowania

## Status identyfikacji

Na podstawie odczytów Deye („LV 3-Phase Hybrid Inverter”, 48 V, trójfazowy 15 kW, sześć programów TOU) **najbardziej prawdopodobną** rodziną jest SUN-14/15/16/18/20K-SG05LP3-EU-SM2. **Dokładny symbol z tabliczki znamionowej nie został potwierdzony.** Dlatego poniższe wartości modelu 15 kW są materiałem odniesienia, a nie bezpośrednią konfiguracją limitów sterowania.

Dane producenta: [Deye datasheet 2026](https://www.deyeinverter.com/deyeinverter/2026/04/26/BDatasheetSUN-14-20K-SG05LP3-EU-SM220260424en.pdf), [manual 14–20 kW](https://nastechsolar.com/content/INVERTERS/DEYE/MANUAL/Manual%20SUN-%2814-20%29K-SG05LP3-EU-SM2.pdf).

## Jeśli tabliczka wskazuje SUN-15K-SG05LP3-EU-SM2

| Właściwość katalogowa | Wartość |
| --- | ---: |
| Moc znamionowa AC | 15 000 W |
| Maksymalna moc pozorna AC | 16 500 VA |
| Zakres napięcia baterii | 40–60 V |
| Katalogowy maks. prąd ładowania/rozładowania baterii | **280 A** |
| Maksymalny ciągły prąd AC pass-through | 70 A |
| Maksymalny prąd wej./wyj. AC | 25/24 A (zależnie od napięcia) |
| Harmonogram baterii | 6 programów TOU |
| Komunikacja | Wi‑Fi / RS485 / CAN |

Uwaga: **350 A jest limitem katalogowym dla wariantu 20 kW w tej rodzinie**, a nie 15 kW. Jednocześnie 280 A katalogowe NIE oznacza, że rzeczywisty BMS Felicity, zabezpieczenie DC, okablowanie, inwerter w danym trybie lub 15 kW przyłącze pozwalają zawsze na taki prąd.

## Znamy nastawy z HA — to NIE są granice sprzętowe

| Encja | Obecny odczyt (07.11.2026) | Znaczenie |
| --- | ---: | --- |
| `number.deye_battery_grid_charging_current` | 40 A | Konfigurowalna nastawa prądu ładowania z sieci |
| `number.deye_battery_max_charging_current` | 200 A | Konfigurowalny ogólny limit ładowania baterii |
| `number.deye_battery_max_discharging_current` | 250 A | Konfigurowalny ogólny limit rozładowania |
| `number.deye_grid_max_import_power` | 31 000 W | Konfigurowalna nastawa Deye, **nie** limit przyłącza |
| `number.deye_grid_peak_shaving` | 8 000 W | Nastawa funkcji peak-shaving; jej aktywność niezweryfikowana |
| `number.deye_program_1_power` | 15 000 W | Limit **rozładowania baterii** w TOU, nie zadana moc ładowania |
| `number.deye_program_1_soc` | 10% | Docelowy/próg SOC programu; znaczenie zależy od Grid Charge/TOU |

Zakres `max=350 A` prezentowany przez encję `number` może być ogólnym zakresem rejestru używanym przez kilka modeli. **Nie jest podstawą do zwiększania maksymalnego prądu falownika.**

40 A × 48 V ≈ 1,92 kW DC, ale jest to przybliżenie **przy aktualnej nastawie**, a nie granica mocy. Prąd zasilania z sieci i moc AC różnią się od prądu i mocy po stronie baterii.

## Ładowanie sterowane automatycznie

- Odczytaj rzeczywisty model Deye z rejestru urządzeń / tabliczki; jeśli nie jest dokładnie rozpoznany, **żadna wartość katalogowa nie jest automatycznie użyta jako limit wykonawczy**.
- Wykryj wszystkie encje związane z przełącznikami `Grid Charge`, `Time of Use`, `program_*_grid_charge`, godzinami, SOC, ograniczeniami prądu. Dwie strony po 40 pozycji w Laboratorium.
- Do wyznaczania mocy ładowania w danej chwili uwzględnij BMS (limit chwilowy), napięcie baterii, maks. moc/inwerter, limity 3 faz, pomiar importu i lokalny limit przyłącza 15 kW, plus bufor.
- Konwersja docelowej mocy DC na prąd: `I = P_DC / U_BAT`. Nie traktuj `Program Power` jako regulacji mocy ładowania z sieci; instrukcja mówi **Max. discharge power of battery allowed**.
- Zapis komendy wymaga odczytu zwrotnego, migawki/rollback, watchdogu i automatycznego zamknięcia przy utracie pomiaru. Aktualna wersja nie wykonuje żadnego zapisu.

## Szczególnie istotne

**Moc znamionowa AC falownika 15 kW i moc przyłączeniowa obiektu 15 kW to nie jest ta sama wielkość.** Wbudowana funkcja przejścia sieciowego (pass-through) może przenosić inną moc. Podłączony EV i pompa ciepła są po stronie Deye LOAD — nie dodawać ich poboru drugi raz.

Zalecany warunek startowy: potwierdzony dokładny model, rozpoznanie brakujących encji TOU/Grid Charge, dostępność odczytu BMS, prawidłowy znak importu, ograniczenia faz, plan testu fizycznego zapisu, pomiar reakcji i przywracanie nastaw.
