# ESTADI Energy Pilot 0.5.5 — rzeczywisty stan Deye TOU (07.11.2026)

## Ustalenia na podstawie 78 regulatorów podanych przez właściciela

| Encja | Stan | Interpretacja |
| --- | --- | --- |
| `switch.deye_battery_grid_charging` | `off` | Globalne zezwolenie ładowania z sieci wyłączone |
| `select.deye_time_of_use` | `Week` | Wybrany wariant dni TOU; semantyka dokładnego wyboru dni zależy od integracji/firmware |
| `select.deye_program_{1-6}_charging` | Wszystkie `Disabled` | Nie ma programu z włączonym ładowaniem Grid/Both |
| `number.deye_program_{1-6}_soc` | Wszystkie 10% | Progi SOC programów; bez aktywnego Grid Charge to nie polecenia doładowania |
| `number.deye_program_{1-6}_power` | Wszystkie 15 000 W | **Ograniczenie rozładowania**, nie moc ładowania z sieci |
| `number.deye_battery_grid_charging_current` | 40 A | Regulowana nastawa prądu ładowania z sieci |
| `number.deye_battery_max_charging_current` | 200 A | Regulowane maksimum ładowania, z dalszymi limitami BMS/hardware |
| `number.deye_grid_max_import_power` | 31 000 W | Nastawa wewnętrzna, **nie** rzeczywisty limit przyłącza 15 kW |
| `switch.deye_grid_peak_shaving` | off | Nie wolno polegać na nastawie `number.deye_grid_peak_shaving=8000 W` jako aktywnym zabezpieczeniu |
| `select.deye_battery_bms_type` | PYLON | Typ protokołu; NIE dowodzi sprawdzenia ograniczeń prądowych BMS |
| `select.deye_battery_control_mode` | Lithium | Bateria litowa |
| `switch.deye_off_grid` | on | Nie interpretować bez potwierdzenia znaczenia tej encji dla konkretnej integracji |

**Nie zmieniaj na tym etapie żadnej nastawy w Deye.** W trybie `Zero Export To Load` i obecnym `Grid Charge off`, włączenie jednego przełącznika bez kontroli reszty programu mogłoby niespodziewanie zmienić sposób pracy magazynu.

## Dlaczego poprzednia lista 78 nie zawierała godzin TOU?

Wykaz dostępnych regulatorów sprawdzał wyłącznie domeny `number`, `select`, `switch`. Godziny startu sześciu programów mogą mieć encje:

- `time.deye_program_1_time` do `time.deye_program_6_time`
- `time.deye_program_1_start`, warianty `time_of_use` i `tou`
- Inne `time.*` przypisane do **tego samego urządzenia Deye** w Home Assistant

Nowe Laboratorium pobiera te encje odczytowo i pokazuje status każdego pola. Jeśli `time.*` nie występuje, otrzymasz komunikat „Brak encji czasu” zamiast sztucznej wartości. W takiej sytuacji należy sprawdzić dokumentację integracji Modbus/Deye, nie zgadywać rejestrów.

## Test z Home Assistant (wyłącznie odczyt)

Po aktualizacji do 0.5.5 i restarcie HA otwórz **ESTADI Energy Pilot → Testy → Programy Deye TOU → Kopiuj mapę TOU**. Wklej raport. Zawiera:

- Globalny Grid Charge i wariant TOU
- Sześć programów: start, SOC, Power, tryb ładowania
- Listę encji czasu i brakujących pól
- Komunikaty blokujące fizyczne sterowanie

Dopiero po takim odczycie możemy zaprojektować sekwencję uruchomienia wraz z bezpiecznym zapisem/przywracaniem. **Wersja 0.5.5 nie wykonuje żadnego zapisu.**

## Źródło producenta

[Deye instrukcja SUN-(14–20)K-SG05LP3-EU-SM2, sekcja 5.7 System Work Mode](https://www.deyeinverter.com/deyeinverter/2026/03/19/rand/8499/%E3%80%90b%E3%80%91manual_sun-14-20k-sg05lp3-eu-sm2_20260319_en.pdf).

Instrukcja podaje sześć przedziałów czasu, osobną aktywację Grid Charge i wybór dni oraz wyjaśnia pole *Power* jako limit rozładowania. Symbol modelu z tabliczki nadal pozostaje niepotwierdzony, więc dane rodziny 14–20 kW są materiałem odniesienia, nie automatycznie obowiązującą konfiguracją.
