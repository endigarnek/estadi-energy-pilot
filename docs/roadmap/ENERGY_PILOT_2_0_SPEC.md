# ESTADI Energy Pilot 2.0 — specyfikacja wdrożenia
**Data:** 2026-11-06  
**Status:** zaakceptowany kierunek funkcjonalny, do implementacji etapowej  
**Baza:** istniejąca integracja v0.2.7 — wyłącznie doradcza  
**Cel:** minimalizować koszt zakupu energii, zachowując bezpieczeństwo falownika Deye, rezerwę magazynu i komfort domowników.

> **Zasada nadrzędna:** nic nie zapisuje ustawień Deye automatycznie, dopóki użytkownik nie włączy trybu automatycznego i urządzenie nie przejdzie kontroli zgodności, testu dry-run oraz odczytu zwrotnego. Nie usuwać ani nie modyfikować obecnego harmonogramu bez kopii, weryfikacji i możliwości przywrócenia.

## 0. Sprawdzony stan i dług techniczny

- HA zintegrowany z Deye, PV, domem, pompą ciepła, ładowarką EV 11 kW i Forecast.Solar, prognozą temperatury Met.no. W v0.2.7 działa odświeżanie/logi/wyliczanie dwóch celów SOC.
- Aktualny `engine.py`: stała moc bazowa 400 W + model pompy; dwa sztywne okna 07–13/16–21; wyliczenie SOC na podstawie niedoboru PV bez symulacji zasobu w kolejności czasowej. **Nie nadaje się jeszcze do produkcyjnego sterowania.**
- Aktualne zarysy godzin odpowiadają zimowemu G13, **nie** domyślnemu G12w! Dla TAURON G12w przykładowo taniej: pn–pt 22–06 i 13–15, weekendy/święta cała doba; G13 zimą: 21–07 i 13–16, latem: 22–07 i 13–19. Każdy profil musi mieć dostawcę, okres obowiązywania, kalendarz świąt i ręczny override.
- Dotychczasowe 45 dni historii z próbek 15-min i `forecast` zamrażany o 21:00 utrzymać. Pomiar energii PV z mocy co 15 min ma być uzupełniony o licznik `sensor.deye_total_production` i liczniki Deye import/eksport/bateria/zużycie. Rejestry energii licznikowej sprawdzać na skoki/reset/zmianę jednostki.
- Czujnik ładowarki `sensor.moc_ladowarki_poprawna` działa (10 A ~6,9 kW), inne surowe sensory ładowarki nie są wiarygodną podstawą oszczędności.

## 1. Wymagania użytkownika — zakres

1. Uczyć się z minimum kilku dni historii, a następnie 14–30 dni z historią kroczącą (minimum 7 pełnych dni do oceny; wcześniej przewidywanie ostrożne). Pralka, piekarnik, kuchenka, zmywarka, klimatyzacja itd. nie będą stałą mocą; model ma opierać się na faktycznym profilu godzinowym i marginesach skoków.
2. Pompa: jeśli istnieje wiarygodny pomiar Shelly, prognozować jej zużycie z godzinowej prognozy temperatury oraz historii, NIE stale 600/1200 W. W razie braku historii używać ostrożnego modelu +8°C / −5°C. Uwzględnić CWU, odszranianie i sezonowość jako zmienność nierozpoznaną, nie udawać przewidywania urządzeń.
3. EV: wykrywać aktywne ładowanie i energię z własnego sensora, **wyłączać EV z modelu typowego zużycia domu**, ale w realnym bilansie sieci, magazynu i kosztów uwzględniać je nadal. Założenie użytkownika: EV ładowane tylko w taniej taryfie. Model musi rozpoznać, czy `sensor.deye_load_power` fizycznie obejmuje EV; jeśli tak, `dom_bez_EV=max(0,dom-EV)`; jeśli nie, nie odejmować. Żadnego domysłu na podstawie samej nazwy encji.
4. G12w/G13 + własna taryfa: ręczne godziny, dni tygodnia, święta, lato/zima, dowolne strefy, ceny PLN/kWh, wersjonowanie dat obowiązywania, osobno import, eksport (net-billing/rozliczenia), koszty stałe i ewentualny koszt degradacji magazynu; NIE wpisywać fikcyjnych cen.
5. Prognoza cenna: symulator SOC krok po kroku (preferowane 15 min, 24–48 h do przodu, aktualizacja co 15 min), uwzględnienie ograniczeń mocy ładowania/rozładowania, pojemności użytecznej, rezerwy, sprawności, temperatury baterii (jeśli dostępna) i mocy całej instalacji.
6. Wizualizacje: duży panel „Energia i plan” i **mały kafelek Lovelace** z aktualnym statusem, decyzją, skutecznością prognoz, kosztami, kolejnym tanim oknem, datą ostatniego pomiaru.
7. Rzeczywiste sterowanie Deye: tryb Doradczy / Symulacja (dry-run) / Automatyczny. Wyraźny przełącznik **„Włącz automatyzację”**, domyślnie WYŁĄCZONY. Osobny przycisk „Zastosuj plan teraz” po potwierdzeniu. Tryb automatyczny dopiero po sprawdzeniu odczytu zwrotnego i manualnym aktywowaniu.
8. Wiarygodność: archiwalne prognozy zamrożone dzień wcześniej, przedziały ufności, metryki skuteczności, weryfikacja symulacji vs pomiary, oznaczanie dni o niepełnych danych oraz log działań i przyczyn.

## 2. Źródła Home Assistant — z istniejącej instalacji

| Funkcja | Encja / integracja | Uwagi |
|---|---|---|
| Moc PV | `sensor.deye_pv_power` | W |
| Zużycie domu | `sensor.deye_load_power` | W; zweryfikować, czy obejmuje EV i pompę |
| Moc pompy | `sensor.shellyem3_08f9e051e0b0_channel_b_power` | W; osobny sygnał treningowy |
| Moc EV | `sensor.moc_ladowarki_poprawna` | W; unikać surowego błędnego sensora |
| SOC | `sensor.deye_battery` | potwierdzić atrybut % i odświeżanie |
| Moc baterii | `sensor.deye_battery_power` | znak ładowania vs rozładowania kalibrowany |
| Import/eksport | `sensor.deye_grid_power`, `sensor.deye_today_energy_import`, `sensor.deye_today_energy_export` | zweryfikować znak i liczniki |
| Produkcja PV — liczniki | `sensor.deye_today_production`, `sensor.deye_total_production` | kWh, walidacja jednostki |
| Bateria — energia | `sensor.deye_today_battery_charge`, `sensor.deye_today_battery_discharge` | kWh |
| Zużycie — energia | `sensor.deye_today_load_consumption`, `sensor.deye_total_load_consumption` | kWh |
| Prognoza PV | Forecast.Solar `forecast_solar.get_forecast` | dane godzinowe, snapshot z dnia poprzedniego |
| Pogoda | encja „Dom” (Met.no) + temperatura zewnętrzna pompy | godzinna temperatura prognozowana |
| EV status | `sensor.ev_charger_11_kw_status` | charging/waiting itd., opcjonalnie |

**Sterowanie Deye — kandydaci, NIE WŁĄCZAĆ BEZ WERYFIKACJI:** `switch.deye_battery_grid_charging`, `select.deye_time_of_use`, `select.deye_program_1_charging` ... `select.deye_program_6_charging`, `number.deye_program_1_soc` ... `number.deye_program_6_soc`, `time.deye_program_1_time` ... `time.deye_program_6_time`, odpowiednie moce i tryb pracy. Istnienie encji nie gwarantuje jednak działania zapisu dla konkretnej wersji firmware/falownika. Nie używać rejestrów raw bez mapy i kontroli modelu.

## 3. Architektura modelu danych i uczenia

### 3.1. Rozdzielenie mocy i źródeł
- Rozróżniać `house_measured`, `ev_measured`, `heat_pump_measured`, `house_baseline_ex_ev`, `non_hp_non_ev`, `pv_forecast`, `pv_actual`, `grid_import/export`, `battery_charge/discharge`.
- Jednorazowy test topologii: gdy EV startuje / kończy ładowanie, porównać skok EV z Deye Load, Grid, Battery i PV oraz wskazać użytkownikowi „EV wliczony / EV poza Load / niepewne”. Do czasu rozstrzygnięcia **nie odejmować EV automatycznie**, wyraźnie oznaczyć ograniczoną wiarygodność symulacji.
- Pompy nie odejmować od zużycia domu drugi raz, jeśli pełna moc domu zawiera pompę; kategorie są rozbiciem na części, a nie dodatkowymi składnikami do zsumowania.
- Sensor 11 kW to moc maksymalna EV, a nie ciągła. Moc treningowa i energia EV wyłącznie z poprawnego sensora; brak danych => brak rekonstrukcji z 11 kW.

### 3.2. Historyczny profil co 15 minut
- Bufor próbek (15 min), agregacja godzinowa + agregat dobowy, min. 90% pokrycia do uczenia; docelowe utrzymanie 90 dni granularnie i 365 dni agregatów (z konfigurowalną retencją). Zachować kompatybilność istniejącego archiwum 45 dni.
- `roboczy / weekend / święto`, godzina, pora roku, przedziały temperatury, profil dnia; minimum 7 pełnych dni, w miarę danych preferować 14/30 dni z malejącą wagą starszych obserwacji.
- Dom bez EV i (dla modelu podziału) bez pompy: mediana krocząca P50, P80/P90 dla godzin o skokach; EMA / exponential smoothing dla najnowszych dni; bez własnego LLM w pętli sterowania.
- Pralki/piekarnika nie „rozpoznawać” bez dodatkowego licznika: traktować jako statystyczne **zdarzenia szczytowe**, generować scenariusze P50 i ostrożny P90; osobny opcjonalny czujnik urządzenia poprawi jakość.
- Pompa: regresja/lookup na temperaturze + porze dnia + dniu roku + załączonych pomiarach mocy; tryb CWU / defrost jako niepewność. Gdy pompa jest off, nie wywnioskować, że nie będzie ogrzewania przez cały dzień. Weryfikować błąd w kWh dla każdego zakresu temperatur.
- Samouczenie: korekty najwyżej raz dziennie, wymuszone przez „Przelicz model”; status „za mało danych”, „uczę się”, „wiarygodność średnia/wysoka”. Nie automatyzować na podstawie pojedynczego dnia.

### 3.3. Poprawna symulacja bilansu SOC
Dla kroku t o długości Δh:
- `load(t) = home_without_ev(t) + EV_planned_or_actual(t)` tylko dla *rzeczywistej symulacji przepływów*; w modelu przeciętnego zużycia `EV=0`.
- `surplus(t)=max(0,PV(t)-load(t))`; `deficit(t)=max(0,load(t)-PV(t))`.
- `E_batt(t+1)=clamp(E_batt(t)+charge_from_PV*η_charge+charge_from_grid*η_charge−discharge_to_load/η_discharge, E_min,E_max)`.
- Ograniczenia mocy kW, prądu BMS, SoC, eksportu/importu, taryfy i źródeł ładowania; odróżniać zakup sieciowy i ładowanie ze słońca.
- Warianty: słoneczny / bazowy / pochmurny + zdarzenia dużych odbiorników; preferować bezpieczne zarządzanie przy zachmurzeniu, nie ładować na zapas jeśli to przynosi straty.
- Nie wolno wyliczać docelowego SOC wyłącznie z sumy dobowej PV: energia o 12:00 nie zaspokoi poboru z 7:00 bez wcześniejszego zapasu.
- Optymalizator rolling horizon 24/48 h i replan co 15 minut; zaproponować tylko zmianę potwierdzoną w symulacji i z wystarczającymi danymi.

## 4. Taryfy i ceny: G12w, G13, własna

**Nie kodować na sztywno obecnych okien 21–07 / 13–16 jako G12w.**

Konfigurator taryfy:
- Dostawca/operator (np. TAURON), profil G12w/G13/„Własna”, strefy `start`, `end`, `dni`, `sezon`, `święta`, zakres dat obowiązywania i strefa `Europe/Warsaw`, w tym zmiana DST i 23/25-godzinna doba.
- G12w (TAURON, do potwierdzenia umową): taniej pn–pt 22:00–06:00 i 13:00–15:00; weekendy i święta cały dzień.
- G13 (TAURON, do potwierdzenia umową): zimą 21:00–07:00, 13:00–16:00 poza szczytem; szczyt przedpołudniowy 07:00–13:00; szczyt popołudniowy 16:00–21:00; latem 22:00–07:00, 13:00–19:00 taniej; pozostałe droższe — zgodnie z oficjalnym cennikiem i taryfą z faktury.
- Formularz cen **brutto PLN/kWh łączny koszt zmienny = energia czynna + dystrybucja zmienna + podatki/opłaty zmienne**, osobno cena za eksport/rozliczenie, osobno opłaty stałe; nie mylić ceny energii z finalnym kosztem importu.
- Osobna zakładka „Porównaj taryfy”: symulacja tego samego rzeczywistego profilu 30/60 dni na G12w i G13, z uwzględnieniem okresu letniego i sezonów; opłaty stałe/dodatkowe tylko tam, gdzie istotnie różnią się między taryfami. Bez obiecywania oszczędności bez cennika.

## 5. Jak dokładnie policzyć oszczędności

Zachować **trzy różne scenariusze**, nie mylić ich:
A. `bez magazynu` (ten sam dom, EV, pompa, PV i eksport; bez strat baterii) vs B. `magazyn — bieżący harmonogram` vs C. `magazyn — plan optymalny`.
- **Wartość magazynu** = koszt A − koszt B (koszt z sieci import minus wartość eksportu, sprawność i opłaty zmienne).
- **Dodatkowy zysk algorytmu** = koszt B − koszt C, osobno jako przewidywany i faktycznie potwierdzony.
- Dodatkowo `koszt ładowania z sieci`, `energia z PV w magazynie`, `energia oddana z magazynu`, `straty`, `cykle`; koszt zużycia baterii (opcjonalne PLN/kWh throughput), jeżeli użytkownik go poda.
- Nie wliczać dwukrotnie pompy i EV, nie liczyć prognoz jako zrealizowanych oszczędności. Dokładność wyników uzależnić od pomiarów licznikowych i danych o eksporcie.
- Raport dzienny, tygodniowy, miesięczny: koszt bez magazynu, rzeczywisty, z algorytmem, oszczędność brutto/netto, wpływ energii z PV, udział tanich godzin, procent redukcji drogich zakupów. Etykieta „szacunek”, jeśli brakuje którejś części danych.

## 6. Ładowanie EV i „drenowanie” magazynu

- EV ładowane zwykle w taniej taryfie, z encji `sensor.ev_charger_11_kw_status` i `sensor.moc_ladowarki_poprawna`; historyczny profil domu **nigdy nie obejmuje typowych poborów EV**.
- Rzeczywisty EV wpływa na fizyczny przepływ energii. Nie wolno go pomijać z bilansem mocy: gdy EV pobiera 6,9 kW, część może chwilowo pochodzić z baterii.
- Funkcja polityki: **„W taniej strefie nie rozładowuj magazynu na samochód”** (domyślnie włączona w propozycjach, realizacja dopiero po potwierdzeniu właściwej konfiguracji Deye). Należy sprawdzić, czy falownik pozwala zatrzymać rozładowanie magazynu w tej strefie przez TOU/min. SOC, bez ubocznego odcięcia zasilania domu lub konfliktu z PV; nie gwarantować, że da się odseparować EV od wszystkich odbiorników.
- Polityka przy ograniczeniu mocy z sieci: unikać jednoczesnego ładowania samochodu 11 kW i baterii, jeżeli przekroczony zostałby limit przyłącza/bezpieczników. Ładowarki EV nie przestawiać automatycznie w MVP; użytkownik decyduje o osobnej przyszłej automatyzacji EV.

## 7. Tryby pracy i bezpieczeństwo sterowania Deye

### 7.1. UI
- `Doradczy` (domyślny): pokazuje plan, nic nie zapisuje.
- `Symulacja` (dry-run): wyświetla co i kiedy zostałoby zmienione, zapisuje decyzje do logów, nie wysyła żadnych poleceń.
- `Automatyczny`: osobny **przełącznik „Włącz automatyzację”**, domyślnie OFF + potwierdzenie, podgląd urządzeń i zapis kopii ustawień. Opcja ręcznego `Zastosuj teraz` z podglądem zmian.
- Widoczna blokada: „NIE GOTOWY — nieznana mapa TOU / brak SOC / brak taryfy / zbyt stara prognoza / błąd odczytu zwrotnego”.
- Przycisk „Wyłącz i przywróć poprzednie ustawienia” z potwierdzeniem i kontrolą powodzenia; odrębny „Stop” gdy przywrócenie nie może zostać zapewnione.

### 7.2. Walidacja urządzenia (przed jakimkolwiek zapisem)
- Weryfikacja konkretnego modelu i integracji: `SUN-15K-SG04LP5-EU` **wymaga potwierdzenia z tabliczki**; nie wolno zakładać identycznych rejestrów co inne Deye SG04LP3.
- Odczyt 6 programów TOU i konfiguracji pracy; zapis migawki, walidacja zakresów czasu/power/SOC i ustawień Grid Charge / Charging Source; test pojedynczej bezpiecznej zmiany w asyście użytkownika + odczyt zwrotny.
- Maks. liczba zapisów w godzinie i histereza: nie zmieniać ustawień przy różnicy SOC mniejszej niż konfigurowalny próg (np. 3–5 punktów procentowych). Korygować po zmianie danych, a nie przy każdym odczycie.
- Fail-safe: jeśli SOC, stan falownika, taryfa albo prognoza są niedostępne/stare lub pojawi się alarm BMS/awaria sieci -> zatrzymać automatyczne zapisy i przejść do bezpiecznego, ustalonego trybu; **nie wymuszać przywrócenia na ślepo**, jeśli sprzęt nie odpowiada.
- SOC rezerwowy nigdy poniżej zatwierdzonego progu; blackout/off-grid i BMS alarm mają pierwszeństwo.
- Uruchomienie automatyki tylko po 7 dniach wiarygodnej symulacji bez naruszeń zasad, plus ręczne potwierdzenie; po poważnym błędzie wymaga ponownego uzbrojenia. Testować także restart HA i utratę łączności.
- Log audytowy: kiedy/jaki slot, wartość przed/po, przyczyna, źródła danych, user/auto, rezultat zapisu oraz odczytu zwrotnego, czas i ewentualna procedura przywracania.

## 8. Wizualizacja / Lovelace (mobile-first)

### 8.1. Miniwidget na pulpit Home Assistant (mały, czytelny bez dodatkowych dodatków)
- 1 wiersz: ikona stanu + **„Optymalizacja działa / Uczę się / Brak danych / Automatyzacja WŁ.”**.
- 2 wiersz: `SOC teraz → cel na następną tanią strefę` oraz `za X min kolejne tanie okno`.
- 3 wiersz: `PV jutro N kWh`, `trafność 7 dni: MAPE/WAPE lub błąd ±... `, `oszczędność w miesiącu (z pomiarów) ... PLN`.
- Akcja `Zobacz plan` otwiera główny panel. Nie dawać przycisku „Włącz automatyzację” w małym widżecie, żeby uniknąć przypadkowego uruchomienia.
- Bezpieczny fallback na brak historii: „Skuteczność: uczę się (2/7 dni)” zamiast zmyślonego procentu.

### 8.2. Pełny pulpit „ESTADI Energia”
1. **Teraz:** produkcja PV, zużycie domu bez EV, pompa, EV, moc baterii, import/eksport, SOC, status strefy i stan systemu.
2. **Prognoza na dziś / jutro 48h:** krzywe PV (prognoza vs wykonanie), dom P50/P90, pompa, plan EV, ceny godzinowe.
3. **Prognoza magazynu:** linia SOC co 15 min z zacienioną rezerwą, godzinami ładowania z PV i z sieci, kolejnymi punktami decyzyjnymi oraz wyjaśnieniami „dlaczego”.
4. **Taryfy i oszczędności:** koszty porównawcze A/B/C w PLN i kWh, miesięczna historia, porównanie G12w vs G13.
5. **Skuteczność:** weryfikacja prognoz na 7/30 dni — bias, WAPE PV, MAE zużycia, kompletność danych oraz odchylenie SOC.
6. **Dziennik i sterowanie:** stan programu 1–6 Deye, ostatnie decyzje, operacje manualne, przełącznik automatyzacji OFF, przycisk przywracania, akcja „Odśwież teraz”.

Przygotować **standardowy, instalowany z integracją widok/pulpit HA**, nie uzależniać podstawowych wykresów od niestandardowych kart HACS; rozbudowany custom card tylko jako opcjonalne ulepszenie. Po instalacji oferować kreator „Dodaj panel jednym kliknięciem”. Panel mobilny: 1–2 kolumny, wykres przewijany, bez nieczytelnych legend.

## 9. Skuteczność modeli i próby kontrolowane
- Prognozy PV: `PV forecast snapshot at 21:00` vs zmierzona produkcja z licznika Deye dzień później. Metryki: błąd kWh, bias %, WAPE po 7/30 dniach, MAE na 1h; niewystarczające dane -> nie liczyć.
- Popyt domu: model `house_without_ev` vs rzeczywistość, osobno pompa ciepła i „niespodziewane urządzenia”, porównanie z naiwnym modelem stałych 400 W.
- SOC: przewidywany i zmierzony przebieg, przekroczenia rezerwy, godziny niespodziewanego importu; replan gdy obciążenie znacznie odbiega.
- Replay/backtest 30 dni (bez korzystania z prognoz z przyszłości): A brak magazynu / B aktualny harmonogram / C nowy algorytm, identyczne wejścia; szacowane oszczędności + zakres niepewności.
- Testy specjalne: brak EV, EV 6,9 kW 10 A, EV 11 kW 16 A, uruchomienie pralki 2 kW, zimny poranek −5°C, pełne słońce, brak prognozy, DST, święto i weekend, odłączony Deye, opóźniony pomiar, źródło PV 0 nocą, brak danych.

## 10. Kolejność wdrożenia i kryterium ukończenia

**P0 — poprawność (przed sterowaniem):**
1. Cennik + poprawne kalendarze G12w/G13; koszt każdej godziny i wyraźne porównanie.
2. Bilans energii/EV + topologia; liczniki Deye, 15-min recorder, nieprawidłowe próbki.
3. Profil 7/14/30 dni i pompa zależna od temperatury; estymacja zdarzeń domowych.
4. Symulacja krocząca 48h z realną mocą magazynu i nieprzekraczaniem SOC rezerwy.
5. Replay + miary wiarygodności.

**P1 — prezentacja:**
6. Duży pulpit z 4–6 wykresami i mały widżet statusu; konfiguracja z gotowymi encjami; przejrzysty podgląd 24h/48h i historia 7/30 dni.

**P2 — bezpieczne sterowanie (po kontroli sprzętu):**
7. Adapter Deye TOU read-only + identyfikacja modelu, stanów, kopia 6 slotów; dopiero potem test zapisu z użytkownikiem.
8. Dry-run 7 pełnych dni, raport proponowanych zmian i alarmów.
9. Przełącznik „Włącz automatyzację” OFF + ręczne zatwierdzenie; polityka EV w taniej taryfie, zapis i odczyt zwrotny TOU, rollback i watchdog.

**Definicja DONE:** brak zgadywania taryfy/rodzaju pomiarów; realny wykres SOC, weryfikacja PV i zużycia, konkretny raport oszczędności, przycisk odświeżenia/logi; automatyzacja włącza się tylko świadomie, możliwa do bezpiecznego wyłączenia.

## 11. Decyzje wymagane od użytkownika dopiero na etapie aktywacji sterowania
- Faktycznie zawarta taryfa, sprzedawca/dystrybutor, godziny i ceny **z faktury** w PLN/kWh, cena / mechanizm wynagrodzenia za eksport.
- Użyteczna pojemność baterii, rezerwa i limit SOC; maksymalny prąd ładowania oraz moc przyłączeniowa.
- Potwierdzenie wariantu modelu Deye i konkretnej integracji, czy EV jest wliczony w Deye Load, dopuszczalność blokady rozładowania w taniej taryfie.
- Preferowany zakres ryzyka: oszczędności vs rezerwa; po próbach: ręczne uzbrojenie automatyzacji.

## Referencje
- Oficjalne strefy TAURON G12w: https://www.tauron.pl/dla-domu/obsluga-i-pomoc/jestem-klientem/zmiany-w-umowie/zmiana-taryfy/g12w
- Oficjalne strefy TAURON G13: https://www.tauron.pl/dla-domu/obsluga-i-pomoc/jestem-klientem/zmiany-w-umowie/zmiana-taryfy/g13
- Home Assistant — Energy: https://www.home-assistant.io/docs/energy/
- Przykład integracji Deye z TOU (NIE mapa rejestrów potwierdzona dla tego modelu): https://github.com/Developer089/deye-modbus-ha/blob/main/info.md
