# Diagnostyka programów Deye Time of Use — ESTADI Energy Pilot 0.3.6

## Cel i gwarancje

Nowa funkcja automatycznie przeszukuje **istniejące encje Home Assistant** i próbuje odczytać sześć programów Time of Use Deye. Pozwala zobaczyć, które wartości są dostępne, jakie są faktycznie ustawione oraz co trzeba zweryfikować przed przyszłym automatycznym sterowaniem.

**Nic nie zapisuje do falownika.** Nie uruchamia ładowania, nie zmienia prądu ładowania, nie przełącza TOU ani nie używa usług `number.set_value`, `select.select_option`, `switch.turn_on`, `time.set_value`. Wersja 0.3.6 nadal jest doradcza.

## Co zobaczysz po aktualizacji

W Home Assistant → Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → urządzenie:

- **Deye TOU — stan rozpoznania** — `nie_wykryto`, `niekompletne` albo `odczytano_6_programow`.
- **Deye TOU — poprawnie odczytane pola** — maks. 24 wartości (6 programów × 4 pola).
- **Deye TOU — data migawki ustawień** — czas zapisania *pierwszego kompletnego* odczytu.
- **Deye TOU — zmiany od migawki** — liczba zmian od pierwszej migawki (widocznych w HA).
- **Deye TOU — gotowość do automatyzacji** — nadal `NIE — tylko odczyt`.

Atrybuty **Deye TOU — stan rozpoznania**:
- `programy_1_do_6`: czas startu, docelowy SOC, moc, tryb ładowania, źródłowa encja i rezultat walidacji.
- `stan_globalny`: odczytane globalne opcje TOU/grid charging, jeśli istnieją.
- `blokady_uruchomienia`: konkretne brakujące pola i ograniczenia bezpieczeństwa.
- `zmiany_w_ustawieniach`: różnice względem pierwszego kompletnego odczytu.
- `odczyt_o`: czas najnowszego odczytu.

Po pierwszym **kompletnym** odczycie moduł zapisuje do lokalnego `.storage` kopię parametrów. Jeżeli konfiguracja się zmieni, pokaże różnice. **To migawka diagnostyczna, a nie system automatycznego przywracania ustawień.** Przy braku pełnego odczytu nie zapisuje niekompletnej kopii.

## Jak rozpoznawane są encje

Znane wzorce:
- `time.deye_program_1_time`
- `number.deye_program_1_soc`
- `number.deye_program_1_power`
- `select.deye_program_1_charging`

Działa także z wybranymi wariantami `deye_time_of_use_1_...` oraz `deye_tou_1_...`. Sprawdza wszystkie programy 1–6. Nie wybiera losowo spośród dwóch encji o tej samej funkcji: status `niejednoznaczne` oznacza konieczność ustalenia prawidłowej mapy.

**Moc wyrażona w % nie jest przeliczana na kW.** Jeśli Home Assistant zwraca `70 %`, pokazujemy `70 %`; bez znajomości rejestru falownika nie wiemy, ile to odpowiada watom. Brak jednostki jest raportowany jawnie.

**Nie zakłada się modelu falownika** tylko na podstawie nazwy Deye. Tryby `Grid`, `Gen`, `on` i podobne są przedstawione jako odczytane wartości, bez przypisywania im semantyki dla konkretnego firmware.

## Czego wciąż brakuje przed automatyzacją

1. Potwierdzenia modelu Deye, firmware i fizycznego znaczenia wszystkich sześciu programów TOU.
2. Weryfikacji źródeł L1/L2/L3 oraz prądowych ograniczeń faz.
3. Potwierdzenia dopuszczalnej mocy ładowania z BMS magazynu Felicity 28 kWh nominalnie.
4. Zmierzenia opóźnień i bezpieczeństwa **jednego kontrolowanego zapisu** oraz odczytu zwrotnego.
5. Opracowania procedury bezpiecznego wyłączenia automatyki i przywrócenia harmonogramu po błędzie.
6. Testów typu `dry-run` przez co najmniej 7 dni, bez wykonywania komend.

Po instalacji wystarczy sprawdzić nowy sensor **Deye TOU — stan rozpoznania**; jeśli status `nie_wykryto`, a encje Deye są widoczne, trzeba dostosować słownik wzorców do rzeczywistych identyfikatorów z Twojego HA. Nie usuwaj istniejącej integracji.
