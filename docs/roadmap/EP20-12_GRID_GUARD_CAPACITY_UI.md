# EP20-12 — Dynamiczny strażnik przyłącza 15 kW, magazyn 28 kWh i pełna wyjaśnialność

**Data:** 2026-11-06  
**Status:** specyfikacja do wdrożenia; brak aktywnego sterowania w aktualnej integracji  
**Powiązania:** EP20-01 (taryfy), EP20-02 (topologia EV), EP20-04 (bilans SOC), EP20-11 (moc i start ładowania), EP20-08/09/10 (Deye, testy, auto)  
**Potwierdzone przez użytkownika:** przyłącze 15 kW, magazyn **28 kWh NOMINALNIE**, praca SOC **10–100%** (granice edytowalne), ładowanie EV zwykle w taniej taryfie.

## 1. Dlaczego jest to obowiązkowe przed sterowaniem

Samochód trójfazowy 11 kW + pompa 2 kW + pozostały dom 1 kW = ok. **14 kW** jeszcze bez ładowania magazynu. Dołączenie magazynu 10 kW mogłoby zwiększyć pobór do ok. 24 kW, jeśli nie ma wystarczającej PV. Limit 15 kW to wartość przyłącza użytkownika; rzeczywiste zabezpieczenie i dopuszczalny **prąd każdej fazy** należy potwierdzić w warunkach przyłączenia i rozdzielnicy. **Program nie zastępuje zabezpieczeń elektrycznych i nie może zagwarantować braku chwilowych przekroczeń, jeśli źródła danych / sterowanie są opóźnione.**

Dwa niezależne obwody decyzyjne:
- **Planista energii** co 15 minut: optymalny cel SOC, czas startu, moc/koszt w tanich strefach, prognoza EV/PV/dom/pompa, porównanie taryf.
- **Szybki strażnik importu (Grid Guard)**: reaguje na zmianę pomiaru poboru z sieci i zdarzenia EV, pompy, baterii. Odświeżanie docelowe 5–15 s, zależne od rzeczywistych możliwości integracji Deye. *Nie wolno opierać strażnika wyłącznie na obecnym odświeżaniu planisty co 15 minut.*

Przed realnym uruchomieniem: zmierzyć odstęp próbkowania Deye, opóźnienie odczytu z licznika, opóźnienie zapisu i reakcję falownika, odporność na utratę łączności; jeśli nie spełnia wymaganego czasu reakcji, stosować konserwatywny statyczny limit ładowania i zabezpieczenia sprzętowe, bez deklarowania aktywnej ochrony programowej.

## 2. Pomiar, priorytety i źródła

**Źródło prawdy:** rzeczywisty **import energii z sieci** na punkcie przyłączenia, a nie suma osobnych urządzeń i nie całkowity pobór „Load Power” falownika. Należy rozpoznać i kalibrować znak `sensor.deye_grid_power` (import/eksport). Dodatkowo mierzyć `sensor.deye_grid_l1_power`, `sensor.deye_grid_l2_power`, `sensor.deye_grid_l3_power` i możliwie prąd L1–L3 na liczniku głównym/CT. Te encje są kandydatami z wcześniejszej listy — ich znaczenie i miejsce montażu wymagają weryfikacji.

**Priorytet mocy:**
1. Dom i istotne obciążenia (pompa ciepła, kuchenka, piekarnik, sprzęt gospodarczy) — nie przełączać/odcinać.
2. Ładowarka EV: użytkownik domyślnie ładuje w taniej taryfie; ograniczanie jej prądu tylko w osobno autoryzowanym trybie i przy potwierdzonej obsłudze regulacji. Bez tej zgody system nie zmienia EV.
3. Ładowanie magazynu z sieci — moc elastyczna: **pierwsza do redukcji** i pierwsza do wznowienia, gdy zwolni się zapas.
4. Fotowoltaika: bieżąca produkcja zmniejsza *realny import*, ale jej przyszły uzysk nie jest gwarantowany do sterowania zabezpieczeniem. Gwałtowny spadek PV -> natychmiastowa rewizja.

Ważne: pompa i EV mogą już być wliczone w `deye_load_power`. **Nie wolno ich drugi raz dodawać** do mocy domu. Rzeczywisty bilans granicy sieci `P_grid` jest podstawą sterowania, a dane EV/HP służą do prognozowania skoków i wykluczania EV z uczenia zwykłego domu.

## 3. Reguły importu i mocy — projekt algorytmu

Konfiguracja początkowa do weryfikacji na instalacji:
- `grid_connection_limit_kw = 15.0` — edytowalne, nie wolno domyślnie zwiększać.
- `grid_guard_soft_limit_kw = 13.0` **przykładowo**, bufor 2 kW na nagłe odbiorniki i opóźnienie sterowania. Docelowo bufor adaptacyjny z P90 skoków, min. ustalane wg testów instalacji; **nie jest to druga moc przyłączeniowa**.
- `grid_phase_current_limits_a` = wartości z zabezpieczeń, **nie zgadywać**. Bez tych wartości i wiarygodnych pomiarów faz nie aktywować dynamicznego sterowania.
- `battery_charge_kw_current` = **faktyczna zmierzona moc ładowania z sieci**, nie samo ustawienie TOU; ustalić znak i kierunek mocy baterii.
- `battery_charge_kw_hard_max` = minimalny limit wynikający z BMS/prądu/napięcia, Deye, mocy przyłącza, temperatury, wybranego limitu użytkownika.
- `max_action_rate` i stopniowanie zmian dostosowane do sterowania Deye: unikać zmian co 5 s, jeżeli zapis dotyka pamięci nieulotnej lub TOU; w takim przypadku potrzebny natywny ogranicznik lub konserwatywna stała nastawa.

Pseudologika dla stanu stabilnego, bez nagłej zmiany produkcji:
1. `P_import = max(0, podpisany_P_grid)` po kalibracji. Walidacja świeżości, odczytów fazowych, rozpoznanie `grid->charge` i opóźnień.
2. `headroom = P_soft_limit - P_import` — **P_import obejmuje aktualny pobór ładowarki i aktualne ładowanie baterii**. Nie odejmować EV, pompy ani baterii drugi raz.
3. `P_charge_candidate = clamp(P_charge_current + headroom, 0, P_bms_limit, P_deye_limit, P_import_phase_limit, P_user_limit, P_tariff_schedule_limit)`. Zabezpieczenie na skok fazy może wymagać niższego pułapu niż ograniczenie sumy 15 kW.
4. **Gdy import za duży lub EV właśnie startuje:** żądaj szybkiego ograniczenia mocy magazynu; jeśli brak zapasu nawet po `P_charge=0`, ostrzeż i ewentualnie ogranicz ładowarkę EV *tylko po osobnej zgodzie i potwierdzeniu możliwości*.
5. **Gdy EV kończy:** po krótkiej stabilizacji pomiarów, np. 30–60 s, zwiększaj moc magazynu etapami (np. +0,5–1 kW co 20–30 s, jeśli pozwala sprzęt), aż do limitu planisty i bieżącego buforu importu. Modyfikacje mocy muszą mieć histerezę, ograniczoną częstość i odczyt zwrotny.
6. Ładowanie magazynu wolno tylko w dozwolonym oknie, jeśli plan/tryb pozwala; nie wybieraj 0,5 kW przez wiele godzin, jeśli koszt strat jałowych przewyższa korzyści. Nieosiągalny cel zgłaszaj zamiast podnoszenia importu ponad przyłącze.
7. Jeśli dane krytyczne (P_grid, fazy, SOC, status BMS, reakcja Deye) są nieaktualne lub niepewne: **nie zwiększaj mocy**; oznacz `BLOKADA AUTOMATYZACJI`, zatrzymaj zapisy i przejdź do wcześniej zweryfikowanego bezpiecznego profilu. Zwykłe „ustaw 0” też jest zapisem i wymaga znanej, bezpiecznej reakcji Deye.

**Przykład bez PV:** EV 11 kW + pompa 2 kW + dom 1 kW = 14 kW. Magazyn nie może wtedy ładować się z sieci, bo samo obciążenie podstawowe jest blisko limitu. Jeśli EV skończy, zostaje ~3 kW obciążenia; przy buforze 2 kW dopuszczalna moc magazynu wynosi w przybliżeniu 10 kW, ale tylko jeśli *fazy, BMS i Deye* też pozwalają.

**Przykład z ładowaniem już uruchomionym:** gdy `P_import=12 kW` przy magazynie pobierającym `3 kW` i soft limit `13 kW`, kandydat to ok. `4 kW`, a nie 1 kW — nie odejmować istniejącej mocy ładowania drugi raz.

## 4. Nominalna pojemność 28 kWh, SoC 10–100% i rozbudowa

**Potwierdzone:** `battery_nominal_kwh = 28.0`, `battery_soc_min = 10`, `battery_soc_max = 100`.

- Teoretyczny zakres energii między 10% i 100% przy liniowym modelu nominalnym: `28*(100-10)/100 = 25,2 kWh`, **przed** korektą SoH/BMS i bez uwzględnienia strat ładowania.
- Nie utożsamiać 28 kWh nominalnie z istniejącym w v0.2.7 polem `battery_capacity_kwh` opisanym jako *użyteczna pojemność*. Wprowadzić oddzielne pola: **Pojemność nominalna**, **Zakres SOC od–do**, **SoH (%) / autokalibracja**, **Efektywna pojemność z pomiarów (kWh)**, **limit ładowania kW/A**. Model stosuje `E(SOC)=P_nominal*SoH*SOC/100` w granicach BMS, z jawną informacją o niepewności.
- Konfiguracja elastyczna: gdy użytkownik zwiększa nominalną pojemność, **przelicz od razu** cele SOC, kWh doładowania, czas startu, rekomendowaną moc, rezerwę i oszczędności *prognozowane*. Zachowaj historyczne migawki parametrów i nie przeliczaj wstecz historycznej rzeczywistości tak, jakby nowy magazyn istniał od zawsze.
- Nie aktualizować na ślepo ograniczeń BMS i fabrycznych zabezpieczeń, nawet jeśli użytkownik dopuści 100% SOC w interfejsie. Wyświetl `zakres użytkownika 10–100%` oraz `aktywne ograniczenie techniczne` osobno.
- Konieczna **migracja** istniejącej konfiguracji v0.2.7 (domyślnie 15 kWh użyteczne) ze sprawdzeniem i jednorazowym zatwierdzeniem 28 kWh nominalnie; brak zgody = brak automatycznego sterowania, zachowane stare obliczenia jako niezweryfikowane.

## 5. Korekta suwakiem — użytkownik musi widzieć jej skutek

**Proponowane sterowanie główne:** suwak `Korekta zapasu na koniec drogiej taryfy`, od `−15` do `+15 punktów procentowych SOC` (krok 1 p.p.), start `0`.
- Przykład: plan bazowy 45% + korekta +8 p.p. = 53% docelowego SOC. W magazynie 28 kWh i SoH 100% daje to +2,24 kWh zapasu (przed stratami).
- Działanie zawsze ograniczone `SOC min 10% / max 100%`, BMS, limitem przyłącza i wykonalnością harmonogramu. Suwak nie zwalnia z zabezpieczeń. W UI wyświetlić: `korekta +8 p.p. → +2,24 kWh → więcej czasu/mocy ładowania i prognozowany koszt +X PLN`.
- Suwak nie powinien automatycznie znikać po samouczeniu. Oddzielny przycisk `Resetuj korektę` i opcja `Automatycznie koryguj prognozę na podstawie ostatnich 7/14 dni` (adaptacja ma pokazywać własny wpływ oddzielnie, np. **model +5 p.p., ręcznie +8 p.p.**).
- Po zapisaniu korekty natychmiast replan 48h, a na miniwidżecie widoczna ikona `Korekta ręczna aktywna`. Zapisać autora, datę i zmianę celu do dziennika.
- Dodatkowe tryby w konfiguracji: `Oszczędny / Zrównoważony / Ostrożny` jako preset percentyla zapotrzebowania P50/P75/P90, **nie** zastępować nimi jednego prostego suwaka.

## 6. System ma wyjaśniać „co widzi, co zrozumiał, co zrobi”

### Pulpit „Przejrzystość decyzji” — na desktop i mobile

**A. Stan na żywo** (aktualizacja zgodna z realną częstotliwością czujników):
- import z sieci `x/15 kW`, limit roboczy `x/13 kW`, fazy L1/L2/L3 `A`, aktualny bufor `y kW`, dane ważne od `n s`.
- PV aktualnie / prognoza, dom całkowity, dom bez EV, pompa, EV (start/koniec, W i A), magazyn: SOC, kWh, ładowanie z PV vs z sieci, aktywny BMS limit.
- wskaźnik stanu: `Prąd dostępny`, `Zmniejszam ładowanie`, `Czekam na EV`, `Zwiększam po EV`, `Brak danych`, `Blokada`.

**B. Karta decyzji z dowodem**:
- `Planista chciał 8 kW od 13:15 do 14:55`, `EV pobiera 11 kW`, `P_grid=14 kW`, `Grid Guard ograniczył do 0 kW`.
- Po wyłączeniu auta: `EV=0, import=3,1 kW, bufor=9,9 kW`, `po 60s stabilizacji zwiększę ładowanie do 5 kW, potem 7 kW`.
- Kod powodu (np. `GRID_HEADROOM_LOW`, `EV_CHARGING`, `PHASE_L2_NEAR_LIMIT`, `DYE_WRITE_UNVERIFIED`, `BMS_CHARGE_LIMIT`, `TARIFF_ENDING`, `PV_SURPLUS_EXPECTED`); polski tekst, źródła, wartości przed/po i timestamp.
- Dwa wyniki: `co powinienem zrobić` (doradztwo) i `co faktycznie wykonałem` (automatyka, ewentualny readback). Nie pokazywać planu jako wykonanego.

**C. Wykres 24/48h**: planowana i rzeczywista moc importu, 15 kW twarda linia, soft limit, prąd/moc faz, zużycie EV/HP, moc ładowania magazynu, PV, prognoza SOC, strefy taryfowe; na osi zdarzenia START/STOP EV, redukcja magazynu, brak danych. Historia 7/30/90 dni i porównanie w PLN.

**D. Miniwidżet Lovelace** (3 linie, mobile):
`⚡ 10,9/15 kW · wolne 2,1 kW · SOC 45%`
`🚗 EV 6,9 kW · 🔋 magazyn 0 kW (ograniczenie przyłącza)`
`⏱ Start magazynu 14:15, zalecane 5 kW · Auto WYŁ.`
Jeżeli brak danych: `Nieznany import — automatyka zablokowana`, nie fikcyjne `0 kW`.

### Logi i metryki efektywności
- Co 15 min snapshot planu i wejść (źródło, świeżość, niepewność, prognoza PV, SOC, marginesy) + przy każdej decyzji strażnika krótki log z przyczyną.
- Liczniki: `ile razy ograniczono ładowanie przez EV`, `czas czekania na moc`, `maks. zmierzony import`, `maks. prąd fazy`, `ile razy nie osiągnięto celu SOC`, `ile kWh odroczono`, `ile PLN kosztowało dodatkowe doładowanie`; nie sumować zdarzeń tak, by modyfikacja jednego slotu liczyła się wielokrotnie.
- Okresy przechowywania, poziomy DEBUG/INFO/WARN/ERROR, eksport CSV z logów, zachowanie stanu po restarcie; logi ograniczone retencją i bez ujawniania wrażliwych danych instalacji.

## 7. Bezpieczeństwo, ścieżka uruchomienia i testy odbiorcze

**Fazy:**
1. `Read-only`: 15 kW, SOC/SoH, EV/HP/PV, fazy i jakość danych; brak zapisów do Deye, informacja czy sterowanie technicznie wykonalne.
2. `Dry-run`: zapisy decyzji bez komend, testy EV 0/6,9/11 kW, pralka+piekarnik, chmury, faza przeciążona, chwilowy brak danych, start/stop EV, DST, weekend, przeciążenie mimo wyłączonej baterii.
3. `Automatyzacja` **domyślnie wyłączona**: dopiero po potwierdzeniu mapy Deye i dopuszczalnej częstości zapisów, testach na urządzeniu, kopii parametrów, readback, 7 dniach dry-run, ręcznym uzbrojeniu.
4. Brak zaufanego odczytu importu/faz/komendy: nie podnosić mocy, podać alarm, bezpiecznie zakończyć sterowanie zgodnie ze zweryfikowaną procedurą, nie obiecywać ochrony samym oprogramowaniem.

**Testy odbiorcze:**
- EV 11 + HP 2 + inne 1 + żądanie baterii 10 kW bez PV -> limit magazynu 0, komunikat o 14/15 kW oraz małym zapasie.
- EV kończy, pompa 2 + dom 1 -> podnoszenie magazynu stopniowo do co najwyżej 10 kW przy **przykładowym** limicie roboczym 13 kW, jeśli BMS i fazy pozwolą.
- `P_grid=12` przy `P_battery_charge=3`, soft limit 13 -> poprawny docelowy limit ~4 kW, **nie** 1 kW.
- Brak rezerwy fazy L2 mimo sumy importu <15 kW -> redukcja baterii; wykrywanie opóźnienia i braku danych.
- Wzrost nominalnego magazynu z 28 do 42 kWh -> SOC 10–100 daje 37,8 kWh teoretycznej energii w zakresie; prognozowane kWh i czasy ładowania przeliczone, historyczne dane nadal dotyczą poprzedniej pojemności.
- Suwak +8 p.p. -> +2,24 kWh przy 28 kWh i SoH=100% oraz widoczny koszt/zmiana startu; brak obejścia 100% / min10%.
- Zmiana taryfy, godzina 15:00 w G12w, awaria podczas zapisu TOU: bezpieczny lockout, alarm i readback.
- **Pomiar fizyczny podczas testu:** potwierdzić reakcję Deye i urządzeń, bo symulacja nie dowodzi ograniczenia rzeczywistego prądu.
