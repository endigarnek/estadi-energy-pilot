# EP20-11 — Inteligentny dobór mocy i godziny ładowania magazynu 28 kWh
**Status:** specyfikacja zatwierdzonego kierunku; do wdrożenia po modelu G12w/G13, topologii EV i symulatorze SOC.  
**Data:** 2026-11-06  
**Istniejąca integracja:** v0.2.7 nadal jest wyłącznie doradcza.

## Założenie instalacji i krytyczna uwaga o pojemności

- Użytkownik podał magazyn **28 kWh**. Zapisać jako **pojemność nominalną zestawu**, nie mylić z *użyteczną* pojemnością energetyczną.
- **Nie zakładać**, że 28 kWh jest w całości dostępne do pracy; uwzględnić rezerwę SOC, dane BMS i sprawność, rozróżnić wartość nominalną / dostępną / energia do uzupełnienia.
- Obecna wersja modułu ma konfiguracyjne domyślne **15 kWh użytecznej pojemności**; jeżeli użytkownik tego nie zmienił, obecne wyliczenia 30% i 47% SOC mogą być istotnie błędne. Wdrożyć ostrzeżenie i walidację, NIE nadpisywać istniejącej konfiguracji bez potwierdzenia faktycznej pojemności użytecznej.
- Limit 10 kW dla baterii jest na tym etapie **przykładem użytkownika**, nie potwierdzoną mocą dopuszczalną. Faktyczne limity odczytywać z Deye/BMS: SOC, napięcie, prąd, temperatura, moc falownika, moc przyłącza, bilans innych urządzeń.

## Cel

Wybrać nie tylko docelowy SOC, lecz również:
1. **Kiedy rozpocząć ładowanie** z sieci (czas, data, najpóźniejszy bezpieczny start).
2. **Jaką moc w kW** ustawić, aby cel osiągnąć w tanim oknie z rezerwą na odchylenia.
3. Czy opłaca się ładować **wcześniej z umiarkowaną mocą** zamiast krótko z bardzo dużą.
4. Czy ładowanie w ogóle jest potrzebne, skoro zbliża się nadwyżka PV.
5. Co zrobić, jeżeli cel jest **nieosiągalny** (brak czasu, BMS ograniczył prąd, równolegle ładuje auto, zbyt wysoki SOC).

## Kluczowe prawa fizyki i pomiar

- `energy_to_store_kwh = max(0, (target_SOC - current_SOC)/100 * usable_capacity_kwh)`.
- `energy_grid_kwh ≈ energy_to_store_kwh / eta_charge(power, SOC, temperature)`. Sprawność ładowania nie jest stała; oszacować krzywą sprawności ze zweryfikowanych danych przy dostępnych warunkach, z domyślnym ostrożnym przedziałem niepewności (bez deklarowania jednej „najlepszej” mocy).
- Dodatkowy pobór falownika i straty jałowe zależą od **czasu aktywnego ładowania**: bardzo niska moc może być nieefektywna. Z kolei maksymalna moc może powodować większe straty cieplne `I²R` i ograniczenia BMS; optymalny przedział ustalić z danych, a nie na sztywno.
- `net_grid_power = house + EV + charge_from_grid - PV - battery_discharge` musi dotrzymywać limitu importu i zabezpieczeń. Trzeba uwzględnić 3 fazy, bieżącą moc przyłącza i możliwą jednoczesność EV.
- Obecnie nie ma zweryfikowanego pomiaru strat ładowania vs moc. **Nie traktować 3 kW, 5 kW ani 10 kW jako uniwersalnie optymalnych**. W UI udostępnić konfigurowalny preferowany zakres, np. 3–6 kW do kalibracji, dopiero po weryfikacji BMS; moc poniżej minimum preferowanego dopuszczać tylko, jeśli inaczej brak bezpiecznego wykonalnego planu i bilans kosztowy to uzasadnia.

## Harmonogram 15-minutowy i wielokryterialny optymalizator

Wejścia:
- Aktualny SOC i pojemność użyteczna; docelowy SOC na koniec taniej strefy + rezerwa bezpieczeństwa i dopuszczalne SOC.
- Kalendarz G12w / G13 / własna, ceny godzinowe (w tym 3 strefy), dane o weekendach i świętach, 15-min sloty wraz z końcem okna.
- Prognoza PV (Forecast.Solar) i jej niepewność, dom z modelem P50/P90, pompa wg temperatury, aktywne EV w taniej taryfie.
- Maksymalna moc ładowania wg Deye/BMS (ograniczenia zależne od SOC, temperatury, napięcia i prądu), opcjonalna moc minimalna sprawnego ładowania, limit mocy przyłącza.
- Ostatnio zmierzona sprawność i przewidywane straty jałowe; minimum czasu pracy, liczba zmian nastaw i margines bezpieczeństwa np. 10–15 min (do konfiguracji).
- Nie używać energii z przyszłej produkcji PV do pokrycia wcześniejszego deficytu; używać symulatora SOC krok po kroku.

Algorytm:
1. Wyznacz **ile kWh brakuje w magazynie w punkcie końcowym**, biorąc pod uwagę prognozowane ładowanie z PV i zużycie w kolejnych slotach.
2. Generuj wykonalne harmonogramy `start_time, power(t)` na siatce 15 min, np. candidate power od zatwierdzonego minimum do bezpiecznego limitu co 0.5 lub 1 kW; rozważ też start z wyprzedzeniem i moc stałą/stopniowaną.
3. Symuluj AC->DC z modelowaną sprawnością, czasem postoju/rozruchu, limitem importu, podawaniem energii do domu i auta, rezerwą BMS.
4. Odrzucaj harmonogramy, które nie osiągają SOC na czas, przekraczają limit mocy/prądu, nie zostawiają rezerwy, powodują ładowanie w drogiej strefie bez podstawy bezpieczeństwa lub zwiększają zbędnie ryzyko.
5. Ranking rozwiązań **koszt energii + straty konwersji + koszt degradacji/obciążenia baterii + liczba zmian nastaw + ryzyko nieosiągnięcia SOC**. Koszt degradacji musi być parametrem użytkownika lub jawnym uproszczeniem, a nie fikcyjną kwotą.
6. Wybierz **najtańszy bezpieczny plan**, ale preferuj umiarkowaną moc, jeżeli różnica kosztu jest mała (histereza i deadband). Różnica >X PLN może uzasadniać inną moc.
7. Jeśli nie da się osiągnąć celu, pokaż: `NIEOSIĄGALNY: brak X kWh, maksymalnie Y% do godz. Z`, zaproponuj tylko bezpieczny wariant i nie podejmuj arbitralnego sterowania.
8. Replan co 15 min, przy starcie EV, spadku PV lub zmianie taryfy. Nie koryguj Deye zbyt często: limit zapisów i minimalne trwanie nastawy.

## Przykłady matematyczne (ilustracyjne, NIE rzeczywisty plan)

Wszystkie przykłady używają **28 kWh jako pojemności dostępnej wyłącznie na potrzeby obliczenia** i **η=90% jako ilustrację**, nie zweryfikowanego parametru Deye.

- Z **40% do 80%** potrzeba `28*(0.8-0.4)=11.2 kWh` w magazynie. Przy umownej sprawności 90% zakup energii `11.2/0.9=12.44 kWh`.
- W oknie 13–16 (tylko gdy rzeczywiście jest tanie, np. G13 zimą) rozpoczęcie 13:30 przy mocy ok. 5 kW przez 2.5 h da orientacyjnie 12.5 kWh z sieci i 11.25 kWh do magazynu — cel powinien zostać osiągnięty, ale bez zapasu czasowego; z buforem czasowym należy zacząć wcześniej lub zwiększyć moc nieznacznie.
- Rozpoczęcie 14:00 przy tej samej energii wymaga ok. 6.2 kW przez 2 h; nie trzeba od razu 10 kW.
- Krótsze okno **G12w 13–15** wymaga przy tym samym deficycie ponad 6.2 kW średniej; niedopuszczalne ustawienie ładowania „do 16” w zwykły dzień G12w.
- Jeżeli cel wynosi 80%, magazyn ma 40% i rzeczywisty limit wynosi np. 5 kW, w dwugodzinnym oknie nie osiągnie celu; system musi pokazać ograniczenie.

## Wykresy, miniwidget i wyjaśnialność

Na pełnym pulpicie:
- 15-min prognoza SOC + krzywa mocy ładowania `kW` na osi czasu, w tle strefy taryfowe i przewidywana PV.
- **Plan teraz:** `Cel SOC 80% do 15:00 / 16:00`, `Start ładowania 13:20`, `Moc 4.8 kW`, `Koniec 14:55`, `Najniższy SOC 20%`, `Koszt ~X zł (prognoza)`.
- Porównanie wariantów „wcześniej 5 kW” vs „później 10 kW”: energia, sprawność, przewidywane straty, koszt i szczyt poboru.
- Postęp planu: `zaplanowano`, `czeka na tanią strefę`, `ładuje`, `PV przejęło ładowanie`, `cel osiągnięty`, `brak danych`, `plan nieosiągalny`.

W miniwidżecie:
`SOC 40% → cel 80% | Start 13:30 | Zalecana moc 5.0 kW | Auto OFF`.
Jeżeli brak wiarygodnych danych: `Brak bezpiecznego planu (sprawdź BMS/taryfę)` zamiast proponowanej mocy.

## Testy odbiorcze i ograniczenia sterowania

- Testy porównawcze: 28 kWh, SOC 20/40/60/80, cel 80/90%, ładowanie 3/5/10 kW, okna 2h / 3h / 8h, różne sprawności przy obciążeniu.
- G12w vs G13, dni robocze vs weekendy, poniedziałek po weekendzie, zmiana czasu letni/zimowy, okno kończące się o 15/16/19, lato.
- EV podczas okna: obciążenie 6.9 kW przy 10 A, 11 kW przy 16 A; moc magazynu redukowana gdy ryzyko przekroczenia limitu przyłącza.
- PV nieoczekiwanie duża/mała, chmury, 10 min przed końcem okna, utrata połączenia, wysoki SOC, alarm BMS, bateria zimna.
- Wysoka moc nie może być wybierana tylko dlatego, że jest technicznie możliwa; jeśli niższa moc daje osiągnięcie celu z mniejszym kosztem i obciążeniem, wybierana jest niższa.
- Wykonanie planu można włączyć **dopiero po** adapterze Deye TOU z weryfikacją zapisów, min. 7 dni dry-run i świadomym przełączniku `Włącz automatyzację` (domyślnie OFF).
