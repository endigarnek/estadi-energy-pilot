# ESTADI Energy Pilot 0.3.7 — tryb testowy dry-run

## Dlaczego powstał

Chcemy zobaczyć, **jakie zmiany ładowania magazynu zaproponowałby system**, zanim pozwolimy mu wysyłać jakiekolwiek polecenia do Deye. Dzięki temu można zbadać zachowanie przy:
- magazynie 28 kWh nominalnie, 10–100% SOC,
- przyłączu 15 kW i buforze 2 kW,
- ładowaniu EV 6,9–11 kW (EV jest już wliczony w Deye Load),
- uruchomieniu pompy ciepła i innych dużych urządzeń,
- taryfie G12w i potencjalnym G13.

**Automatyka pozostaje wyłączona. Ta funkcja nigdy nie zapisuje nastaw Deye.**

## Czujniki Home Assistant

Po aktualizacji i pełnym restarcie na urządzeniu ESTADI Energy Pilot pojawią się:

| Sensor | Znaczenie |
|---|---|
| Dry-run — stan testu | `blokada` / `oczekiwanie` / `symulacja` / `cel_osiagniety` / `brak_pomiarow` |
| Dry-run — hipotetyczna decyzja | `czekaj` / `laduj_planowo` / `laduj_z_ograniczeniem` / `wstrzymaj_ladowanie` / `cel_osiagniety` / `poza_tania_taryfa` |
| Dry-run — hipotetyczna moc magazynu | kW, `unknown` jeśli brak zaufanej prognozy/importu |
| Dry-run — zapisane decyzje | Liczba zdarzeń w aktualnie przechowywanym dzienniku |
| Dry-run — kompletne dni testów | Liczba dni z co najmniej 80 **różnymi** 15-minutowymi przedziałami odczytu |
| Dry-run — ostatnia decyzja o | Znacznik ostatniego zapisanego wydarzenia |

W atrybutach **Dry-run — stan testu** zobaczysz:
- **hipotetyczna_decyzja** — cel SOC, moment startu, moc z planisty, ograniczenie Grid Guard, bieżący pobór sieci, EV i przyczyny;
- **ostatnie_20_decyzji** — czas, typ i kod hipotetycznej decyzji, proponowaną i ograniczoną moc, SOC, EV oraz import;
- **dni_pozostale** — ile dni obserwacji brakuje do minimum 7 dni;
- **faktycznie_wyslane_polecenia: 0** — zawsze, ponieważ nie ma żadnej funkcji wysyłania komend.

### Ważne rozróżnienie: blokada a intencja

Przykład:
- Planista chce: `5 kW od 13:15 do 14:55`;
- EV aktualnie: `11 kW`;
- Grid Guard wylicza `0 kW` mocy dostępnej;
- W dzienniku: `hipotetyczna_akcja: wstrzymaj_ladowanie`;
- Status: `blokada`, bo niepotwierdzone fazy/BMS/Deye;
- Wykonane komendy: `0`.

Po zakończeniu ładowania EV monitor może zarejestrować zmianę `wstrzymaj_ladowanie → laduj_planowo` albo `laduj_z_ograniczeniem`, nadal **bez sterowania**.

Jeśli nie ma znaków importu/baterii, wiarygodnej prognozy lub mapy TOU, test nadal zapisuje **przyczyny blokady**. To celowe — system ma pokazać, co jest brakującym warunkiem, zamiast udawać poprawne decyzje.

## Historia i retencja

- Plan ładowania liczy się co 15 minut; Grid Guard i hipotetyczne reakcje są aktualizowane na podstawie lokalnych sensorów co 15 sekund.
- Dziennik zapisuje zmianę ważnej decyzji od razu, a przy braku zmian zachowuje okresowy zapis najwyżej raz na 15 minut.
- Historia w `.storage/estadi_energy_pilot.<entry_id>.dry_run` jest ograniczona do **ostatnich 8 dni i maks. 1000 zapisów**; zachowana po restarcie HA, bez wysyłania do chmury.
- Nie oznaczamy dnia jako pełny na podstawie 80 szybko następujących zmian w tej samej godzinie. Wymagane są co najmniej 80 **odrębnych kwadransów** dziennie.
- Samo zebranie 7 dni **nie włącza automatyki**. To jedynie minimalna historia do oceny jakości działania.

## Co potrzebne do autentycznego sterowania

1. Potwierdzenie znaczenia i jednostek TOU w konkretnym firmware Deye i zapis/odczyt zwrotny pojedynczej wartości na żywym urządzeniu.
2. Sprawdzenie mocy na każdej fazie i rzeczywistych zabezpieczeń elektrycznych.
3. Potwierdzenie limitów prądowych BMS i falownika oraz szybkości reakcji na zmianę ładowania.
4. Dokończenie symulatora opłacalności i testów w sytuacji zaniku sieci, odłączenia EV i błędnych sensorów.
5. Osobna decyzja użytkownika o uruchomieniu automatyki, potwierdzenie i bezpieczna procedura przywrócenia wcześniejszych ustawień.

**Tej wersji nie należy traktować jako ochrony przeciwprzeciążeniowej.** Brak poleceń do sprzętu jest celowy.
