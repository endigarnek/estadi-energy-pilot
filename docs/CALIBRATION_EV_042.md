# ESTADI Energy Pilot 0.4.2 — kalibracja domu, PV i scenariusz EV

Wersja 0.4.2 dodaje **analizę wiarygodności modelu** oraz osobny **historyczny wariant ryzyka ładowania samochodu**. To wyłącznie funkcje doradcze. Moduł nie wysyła poleceń Deye ani ładowarce i nie zmienia automatycznie stawek, korekt czy harmonogramu.

## 1. Czy profil domu prawidłowo przewiduje zużycie?

Silnik `load_calibration.py` analizuje maksymalnie 30 ostatnich dni lokalnej historii Deye Load, osobnych odczytów EV i pompy ciepła. Dla każdej godziny:

- sprawdza, czy mamy **co najmniej 90% czasu pomiaru** na wszystkich wymaganych sensorach;
- oblicza zużycie bazowe = **Deye Load minus EV minus pompa** — oba odbiorniki są już wliczone do Deye Load, dlatego nie mogą być dodane ponownie;
- ignoruje niemożliwe godziny, w których pobór samochodu przekracza cały odczyt Deye Load;
- **testuje dzień na danych z poprzednich dni tego samego typu** (roboczy lub weekend/święto). Minimum 3 wcześniejsze dni do utworzenia prognozy danej godziny. Dzień testowany nigdy nie uczestniczy w swoim trenowaniu;
- pokazuje **MAE w kWh na godzinę**, WAPE (%), średnie odchylenie prognozy oraz liczbę ocenionych godzin.

Status `oceniono` wymaga minimum **3 ocenionych dni oraz 72 porównanych godzin**. Przy mniej kompletnej historii wyświetli `zbieranie_danych` i nie będzie deklarować trafności.

Ten etap **nie zmienia automatycznie prognoz** ani mocy ładowania. Zebrane wyniki pozwolą ocenić, czy mediana godzinowa jest wystarczająco wiarygodna i gdzie występują błędy. Wariant ostrożny P90 w aktualnym modelu pozostaje bez zmian.

## 2. Kalibracja Forecast.Solar / Solcast

Z zamrożonych wieczorem prognoz i zakończonych dni z kompletną produkcją PV liczymy stosunek **rzeczywista produkcja / prognoza**.

Po **co najmniej 7 porównywalnych dniach** moduł pokazuje sugerowaną **całkowitą korektę PV 0–40%**. Na przykład: jeśli suma prognoz wyniosła 100 kWh, a produkcja 80 kWh, rekomendacja to 20%.

**To sugestia łączna, nie dodatkowe 20% do już ustawionego rabatu.** Nie stosujemy jej automatycznie. Możesz ją porównać ze swoim obecnym `pv_discount_pct` w opcjach zaawansowanych.

Nie tworzymy korekty z niepełnych dni ani prognoz poniżej 0,5 kWh. Wynik może zmieniać się wraz z porą roku, zacienieniem i zachmurzeniem; nie oznacza kalibracji certyfikowanej.

## 3. Jak uwzględniamy nieznane przyszłe ładowanie EV?

Wprowadzamy **trzeci, oddzielny wariant stresowy** do istniejących dwóch strategii ekonomicznych magazynu:

- bez ładowania magazynu z sieci i z historycznym obciążeniem EV;
- z zaplanowanym ładowaniem magazynu i z historycznym obciążeniem EV.

Historia musi zawierać **minimum 7 kompletnych dni EV**, a wśród nich **co najmniej 3 dni robocze i 3 dni wolne**. Brak pomiarów nie jest traktowany jako 0 kWh.

Dla każdej godziny i typu dnia liczony jest **90. percentyl (P90) zaobserwowanej energii samochodu w kWh/h**. Silnik rozkłada godzinową wartość na cztery kwadranse w symulacji 48h.

**Ważne:** zestawienie godzin P90 z osobnych dni może łączyć sesje, które nigdy nie wystąpiły razem. To **test obciążenia**, a nie prognoza konkretnej wizyty samochodu, prawdopodobieństwo ani znany harmonogram ładowarki.

- Pierwszy kwadrans wykorzystuje **bieżący odczyt EV**; historyczny profil nie jest do niego dodawany.
- Historyczne EV jest doliczane tylko w **osobnej symulacji stresowej**, nie do podstawowej prognozy ani planowanego harmonogramu Deye.
- Import, energia EV, końcowy SOC i koszt importu pokazują wpływ hipotetycznego kolejnego ładowania auta.
- **Deye Load już obejmuje samochód i pompę** — historia bazowa ma je odjęte, więc nie liczymy ich dwukrotnie.
- Wariant stresowy nadal respektuje ograniczenie planowanego ładowania magazynu: **15 kW przyłącza minus 2 kW bufora**. Jeżeli sam dom/EV przekroczy limit, symulator pokaże przekroczenie, nie ograniczy fizycznie EV.
- **Nie liczymy zrealizowanych oszczędności** ani nie wydajemy na tej podstawie poleceń do falownika.

## 4. Nowe sensory Home Assistant

Po aktualizacji i ponownym uruchomieniu HA na urządzeniu ESTADI Energy Pilot znajdziesz:

| Sensor | Znaczenie |
|---|---|
| Kalibracja — stan oceny modelu domu | Czy jest dość uczciwych porównań |
| Kalibracja — błąd profilu domu | MAE w kWh/godzinę |
| Kalibracja — WAPE profilu domu | Błąd względny w % |
| Kalibracja — przetestowane godziny | Liczba porównanych godzin |
| Kalibracja — sugerowana całkowita korekta PV | Propozycja %, nie wykorzystywana automatycznie |
| EV — stan historycznego scenariusza ryzyka | Czy profil stresowy jest gotowy |
| EV — liczba dni pełnych pomiarów | Postęp historii EV |
| EV — szczyt stresowy z historii | Najwyższa średnia moc w godzinie, kW |
| Opłacalność — import z planem i ryzykiem EV | Import przy nieznanej sesji EV w kWh |
| Opłacalność — SOC z planem i ryzykiem EV | Końcowy SOC w scenariuszu stresowym |

Atrybuty **Kalibracja — stan oceny modelu domu** zawierają liczby, brakujące warunki i godzinowe profile EV. W **Opłacalność 48h — status** jest dodatkowy atrybut `historyczny_wariant_ryzyka_EV`, z podsumowaniem obu strategii oraz ostrzeżeniami.

Nowe bloki **„Kalibracja prognoz i niepewność EV”** oraz **„Co jeśli auto znowu będzie się ładować?”** zostały dodane do generatora pulpitu. Aby je zobaczyć, naciśnij ponownie przycisk **„Wygeneruj pulpit, miniwidżet i wykres 48h”** i skopiuj nowy plik YAML do dashboardu. Starszego pliku nie nadpisujemy.

## 5. Ograniczenia

- Do oceny modelu potrzebujemy rzeczywistych odczytów przez kilkanaście dni. Jeśli Home Assistant jest wyłączony albo sensory EV nie mają ciągłych pomiarów, status `zbieranie_danych` jest poprawny.
- Bez wskazania faktycznego EV i pompy nie można odjąć ich od Deye Load, więc kalibracja nie powinna udawać wiarygodności.
- P90 opisuje osobne godziny — **nie jest** bezpiecznym limitem prądowym faz ani górnym ograniczeniem możliwego przyszłego zużycia.
- W tej wersji **nie uczymy temperatur pompy** z historii, bo zapis historyczny nie zawiera jeszcze zmierzonej temperatury dla każdego kwadransa. Będzie to osobne zadanie.
- **Korekta PV nie włącza się automatycznie**: najpierw trzeba zaobserwować jej stabilność w różnych warunkach.
- G12w/G13 i ceny dalej zależą od danych wpisanych przez użytkownika. Brak potwierdzonych cen = brak kosztów w złotówkach.
- Sterowanie Deye i ładowarką EV pozostaje wyłączone, `automatic_ready=false`.
