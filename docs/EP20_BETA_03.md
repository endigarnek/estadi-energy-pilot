# ESTADI Energy Pilot 0.3.0 — aktualizacja beta

**To pierwsza implementacja Energy Pilot 2.0, tylko do odczytu i obliczeń. Nie steruje falownikiem Deye.**

## Co jest gotowe

- Magazyn **28 kWh nominalnie**, zakres SOC **10–100%**, szacowany SoH 100%, dwa suwaki do edycji pojemności i ręcznej korekty SOC.
- Taryfy TAURON G12w / G13 z poprawnymi godzinami, weekendami, świętami i sezonowością.
- Grid Guard: odczyt mocy na przyłączu, limit 15 kW i bufor 2 kW; **nie sumuje dwukrotnie EV i pompy**.
- Orientacyjny plan ładowania: start, moc kW i cel SOC — tylko gdy istnieją wiarygodne odczyty i tanie okno.
- Sensory importu, zapasu, statusu, przyczyny blokady, strefy taryfy i planu.

## Aktualizacja i konfiguracja

Marketplace / HACS → ESTADI Energy Pilot → Aktualizuj / Pobierz ponownie → **restart Home Assistanta** → istniejąca integracja → Konfiguruj.

**Wymagana kalibracja przed zaleceniem mocy:**
- Sprawdź, czy `sensor.deye_grid_power` to moc na granicy sieci i czy podczas importu jest dodatnia czy ujemna.
- Sprawdź, czy `sensor.deye_battery_power` ma dodatni czy ujemny znak podczas ładowania.
- W ustawieniach zaawansowanych ustaw oba znaki. Bez kalibracji system pokaże **blokadę** zamiast sugerować moc.
- Nie uznaj limitu symulacyjnego 10 kW za rzeczywisty limit BMS. Przed automatyką trzeba zweryfikować moce, prądy faz i reakcję Deye.

**Nie ma jeszcze:** wyuczonego profilu domu 7/14/30 dni, automatycznego wykluczania EV z historii, dokładnej symulacji SOC 48h, faktycznych oszczędności PLN, samoczynnego ładowania ani gotowego graficznego panelu. To kolejne kroki planu.

Ceny energii domyślnie **0 = nieznane**; wprowadź własne stawki brutto PLN/kWh. Brak stawek oznacza brak obliczeń oszczędności — nie pokazujemy fikcyjnych złotówek.

**Pojemność nominalna 28 kWh i zakres SOC 10–100% dają teoretyczne 25,2 kWh w zakresie przy SoH=100%, przed korektami BMS i strat.** Poprzedni parametr pojemności 15 kWh był starym domyślnym ustawieniem i nie jest już wykorzystywany do nowych zaleceń.

Źródła taryf: [TAURON G12w](https://www.tauron.pl/dla-domu/obsluga-i-pomoc/jestem-klientem/zmiany-w-umowie/zmiana-taryfy/g12w), [TAURON G13](https://www.tauron.pl/dla-domu/obsluga-i-pomoc/jestem-klientem/zmiany-w-umowie/zmiana-taryfy/g13).
