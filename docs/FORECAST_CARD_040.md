# ESTADI Energy Pilot 0.4.0 — interaktywny wykres prognozy 48 godzin

## Jak uruchomić nową kartę

Wersja 0.4.0 zawiera własną, bardzo lekką **kartę Lovelace z interaktywnym wykresem SVG**, bez zewnętrznych bibliotek. Po aktualizacji istniejącej integracji przez HACS i restarcie Home Assistant:

1. W panelu urządzenia **ESTADI Energy Pilot** naciśnij **„Wygeneruj pulpit, miniwidżet i wykres 48h”**. Przycisk przygotuje:
   - `/config/estadi-energy-pilot-dashboard.yaml` — pełny pulpit z nowym wykresem i zapasową tabelą,
   - `/config/estadi-energy-pilot-mini.yaml` — miniwidżet,
   - `/config/www/estadi-energy-pilot-forecast-v040.js` — plik interaktywnej karty.
2. **Jednorazowo zarejestruj kartę:** Home Assistant → **Ustawienia → Pulpity → menu trzech kropek → Zasoby (Resources)**, następnie **Dodaj zasób**.
3. W polu adresu URL wklej **`/local/estadi-energy-pilot-forecast-v040.js`**, typ **Moduł JavaScript (JavaScript module)**. Zapisz. W zależności od wersji HA menu zasobów może znajdować się w innym miejscu sekcji Pulpity.
4. Stwórz **nowy pusty pulpit** albo edytuj specjalny pulpit ESTADI z wersji 0.3.9. Wklej cały nowy plik `estadi-energy-pilot-dashboard.yaml` przez **Edytor konfiguracji surowej (Raw configuration editor)**. W razie ostrzeżenia o `custom:estadi-energy-forecast-card` upewnij się, że zasób JavaScript jest poprawnie zarejestrowany i przeładuj przeglądarkę (Ctrl+F5).
5. Jeśli używasz już własnego pulpitu z 0.3.9, możesz **zamiast zastępować cały pulpit** skopiować wyłącznie poniższą kartę, podmieniając ID `sensor.` na ID encji **Symulacja 48h — stan** z Twojego HA:

```yaml
type: custom:estadi-energy-forecast-card
entity: sensor.TUTAJ_FAKTYCZNY_ID_SYMULACJI_48H
title: Prognoza 48h • SOC / PV / dom / sieć
default_series:
  - soc
  - pv
  - dom
  - import
  - pompa
  - auto
```

W eksportowanym pełnym pulpicie **ID jest podstawiane automatycznie z Entity Registry**. Przykładowy YAML powyżej jest tylko instrukcją ręcznego wklejenia jednej karty.

## Co pokazuje wykres

- **Oś lewa:** SOC magazynu (0–100%). **Oś prawa:** energia w każdej godzinie w **kWh** — nie mylić z chwilową mocą w kW.
- **Kolorowe serie:** SOC, fotowoltaika, Deye Load (cały dom), import, eksport, pompa ciepła i samochód EV. Każdą serię można włączyć lub wyłączyć.
- **Zielone tło:** tańsze strefy G12w/G13 wyliczone przez symulator dla dat prognozy (także weekendy i święta).
- **Interaktywność:** wskazanie myszką, dotknięcie wykresu na telefonie oraz lewo/prawo na klawiaturze pokazują wszystkie wartości dla wybranej godziny.
- **48h, nie 192 punktów:** obliczenia w silniku pozostają 15-minutowe, ale wykres prezentuje maksymalnie 48 **godzinnych** wyników, bo tak są już dostępne w atrybucie `harmonogram_48h`. Nie podszywa się pod nieistniejący przebieg co 15 minut.
- **Braki danych:** jeśli prognoza PV urywa się przed końcem 48h, wykres kończy się na ostatnim poprawnym przedziale. Nie rysuje przyszłej produkcji jako wymyślonego zera.
- **DST:** znacznik czasu ma offset (+0100/+0200), więc dwie godziny `02:00` przy zmianie czasu są odróżniane i poprawnie sortowane.
- **EV i pompa:** Deye Load już zawiera samochód i pompę ciepła. Tych wartości **nie dodajemy ponownie** do zużycia całego domu. EV po bieżącym pierwszym kwadransie pozostaje nieznane, dopóki nie powstanie osobny harmonogram ładowania samochodu.
- **Taryfa:** strefa zielona to informacja z G12w/G13, nie obietnica konkretnych cen. Stawki trzeba wprowadzić z własnej faktury.
- **Magazyn:** nadal tylko **scenariusz bez dodatkowego ładowania z sieci**. Zalecany plan ładowania jest prezentowany w innych kartach i nie został jeszcze włączony do wspólnej symulacji 48h.

## Bezpieczeństwo, wersjonowanie, aktualizacje

Generator działa **wyłącznie po kliknięciu przycisku**. Nie wysyła niczego do Deye, nie zmienia konfiguracji ładowarki EV, nie zapisuje tokenów i nie korzysta z zewnętrznych CDN. JavaScript renderuje tylko zawartość sensora Home Assistant — nie posiada kodu wywołującego usługi.

Nie nadpisuje istniejących plików YAML. Jeżeli były już eksportowane, powstają nowe nazwy `-2.yaml`, `-3.yaml` itd. Zasób JS ma **wersjonowaną nazwę** `v040`: jeżeli istnieje identyczny plik, zostaje zachowany; jeżeli samodzielnie go edytowano, przycisk zgłosi konflikt, **nie nadpisze ręcznych zmian**.

Ponieważ Home Assistant może mieć własne niestandardowe zasoby i ustawienia pulpitów, integracja **nie rejestruje automatycznie zasobu Lovelace**. Rejestracja `/local/estadi-energy-pilot-forecast-v040.js` jest jednorazowym krokiem użytkownika. Jeżeli nowej karty nie uda się uruchomić, pełny pulpit nadal zawiera zapasową tabelę prognozy SOC w natywnej karcie Markdown.

**Sterowanie Deye pozostaje wyłączone.** Wykres nie zastępuje Grid Guard, BMS ani zabezpieczeń fazowych. Jego wartości są prognozami, a nie wynikami faktycznego wykonania planu.

## Testy

GitHub Actions uruchamia testy renderowania YAML (PyYAML), testy Python integracji i osobne testy Node.js: rejestracja karty, 48 godzin danych, brakujące wartości, odstępy czasu zimowego, dotyk/klawiatura, włączanie serii, bezpieczne kodowanie HTML i brak ścieżek zapisujących do falownika.
