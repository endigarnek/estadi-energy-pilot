# ESTADI Energy Pilot 0.4.4 — diagnostyka nietypowego poboru pompy

Wersja 0.4.4 rozbudowuje odczyty z 0.4.3 o **wykrywanie historycznych godzin z ponadprzeciętnym zużyciem prądu przez pompę ciepła**. Jest to bezpieczna analiza wyłącznie do odczytu. Nie wysyła poleceń do falownika DEYE, pompy ani ładowarki EV.

## Jak wykrywamy zdarzenia?

1. Korzystamy ze wspólnej historii pomiaru mocy elektrycznej pompy i rzeczywistej temperatury zewnętrznej. Godzina musi mieć **min. 90% pokrycia obu pomiarów**; brakujące godziny są pomijane, a nie uznawane za 0 kWh.
2. Dla każdej zakończonej doby tworzymy referencyjny model temperatury P50/P90 **wyłącznie z dni wcześniejszych niż oceniana doba**. Dane nie przeciekają z ocenianego zdarzenia do modelu, który ma je wykryć.
3. Podwyższony pobór jest oznaczany dopiero, gdy energia pompy w godzinie wynosi co najmniej **1 kWh**, jest o co najmniej **0,65 kWh** większa od historycznej mediany w danym zakresie temperatur i osiąga minimum **135% historycznego P90**. Te progi celowo są ostrożne: pojedyncze drobne wahania nie powinny generować zdarzeń.
4. Sąsiednie godziny z podwyższonym zużyciem łączymy w jeden **okres podwyższonego poboru**; brakująca godzina je rozdziela. Pokazujemy start/koniec, długość, zużycie, sumę dodatniej nadwyżki nad P50 oraz zakresy temperatur.
5. Do wiarygodniejszego zestawienia wymagamy minimum **24 godzin możliwych do porównania**, w tym **3 różnych dni z minimum 6 ocenionymi godzinami**. Dopóki warunki nie są spełnione, status to `zbieranie_danych`, a liczniki zdarzeń i nadwyżki pozostają **nieznane** zamiast przyjmować 0.
6. W atrybutach sensora dostępne jest ostatnich 20 okresów; cała analiza liczona jest na najwyżej 30 dniach, bez osobnej, nieograniczonej bazy zdarzeń. Restart Home Assistanta nie usuwa bazowych pomiarów.

### Czego nie możemy stwierdzić z samego poboru prądu?

Powyższa diagnostyka **nie rozpoznaje z pewnością przyczyny**. Wysoki pobór może towarzyszyć podgrzewaniu CWU, odszranianiu, grzałce elektrycznej, podwyższaniu temperatury pomieszczeń, zmianie sterowania lub usterce. Dopiero osobne czujniki temperatury zasobnika CWU, sygnału pracy sprężarki, trybu odszraniania i/lub grzałki pozwolą nazwać zdarzenia.

**Nie podajemy liczby cykli sprężarki ani liczby odszraniań**, bo godzinowe całki energii nie pozwalają ich odtworzyć. W atrybutach jawnie zapisano `potwierdzone_cykle_CWU: null` oraz `potwierdzone_odszraniania: null`. Nie wolno interpretować `null` jako zera.

## Nowe sensory

| Sensor | Co oznacza |
|---|---|
| Pompa — stan oceny nietypowego poboru | `oceniono_odchylenia` lub `zbieranie_danych` |
| Pompa — porównane godziny | Ile historycznych godzin przeszło warunki jakości |
| Pompa — okresy podwyższonego poboru | Ile okresów pogrupowano w ukończonych dniach |
| Pompa — szacowana nadwyżka poboru | Suma dodatkowych kWh względem temperatury i historycznej mediany |
| Pompa — ostatni nietypowy pobór | Początek ostatniego wykrytego okresu |

Pełny pulpit ESTADI zawiera teraz sekcję **„Pompa — kontrola podwyższonego poboru”** oraz tabelę historycznych okresów. Aby ją zobaczyć, ponownie kliknij **„Wygeneruj pulpit, miniwidżet i wykres 48h”**, a następnie zaimportuj nowy plik YAML. Nie nadpisujemy wcześniejszych pulpitów.

## Co jest potrzebne po aktualizacji?

Zaktualizuj integrację do 0.4.4 i zrestartuj Home Assistanta. Upewnij się, że w opcjach wskazano **faktyczny sensor mocy pompy (W/kW)** i **zewnętrzny sensor temperatury (°C)**.

Historia temperatur skojarzona z pompą jest zbierana dopiero od 0.4.3. Jeśli integracja nie pracowała jeszcze przez odpowiednią liczbę dni, status zbierania danych jest prawidłowy. Starej historii nie uzupełniamy zgadywaną temperaturą.

## Testy i ograniczenia

Testujemy: stabilny pobór bez fałszywych zgłoszeń, dwa oddzielne okresy zwiększonego zużycia, godzinę bez pomiaru między zdarzeniami, brak danych temperatury, nowy/nietrenowany zakres, wykluczenie bieżącego i przyszłego dnia, niewyciąganie wniosków o CWU oraz brak ścieżek sterowania. Dodatkowo w CI sprawdzamy składnię Python, pulpit YAML i Home Assistant hassfest.

Nowa funkcja **nie zmienia wyuczonych wartości pompy w prognozie 48h**, planu ładowania magazynu ani Grid Guard. Jej celem jest pokazanie, skąd mogły się wziąć duże odchylenia poboru oraz przygotowanie gruntu pod dokładniejsze sensory CWU i odszraniania w kolejnym etapie.
