# ESTADI Energy Pilot 0.4.3 — analiza pompy ciepła według temperatury

## Co jest nowego

Od wersji 0.4.3 system zapisuje **temperaturę zewnętrzną w tym samym przedziale czasu co rzeczywiste zużycie elektryczne pompy ciepła**. Dzięki temu można budować model zużycia oparty na realnej pracy pompy, a nie wyłącznie na dotychczasowym prostym wzorze z wartościami mocy przy cieplejszej i chłodniejszej pogodzie.

**Ważne:** poprawny historyczny model może zacząć powstawać **dopiero po aktualizacji do 0.4.3**. Nie odzyskujemy temperatur z wcześniejszych zapisów zużycia, ponieważ nie znamy temperatury dokładnie w godzinach starych pomiarów.

## Jakie pomiary są wymagane

- W opcjach integracji wybierz **sensor temperatury zewnętrznej (°C)**, najlepiej fizyczny czujnik na zewnątrz. W tej wersji pogoda `weather.*` nadal służy jako fallback do zwykłej prognozy, ale **nie jest automatycznie mieszana** z temperaturą mierzoną na miejscu podczas treningu.
- Wskaż sensor **mocy elektrycznej pompy** w W lub kW. Deye Load obejmuje pompę i samochód, ale do nauczenia zależności pompy od temperatury konieczny jest **osobny pomiar pompy**. Nie należy przypisywać ogólnego Deye Load jako pomiaru pompy.
- System akceptuje tylko świeże odczyty temperatury i mocy (maksymalnie 30 minut od ostatniego raportowania). Przerwy powyżej 30 minut nie są uzupełniane wymyślonymi próbkami.
- Godzina jest porównywalna wyłącznie przy **co najmniej 90% pokrycia osobnym pomiarem mocy i temperatury**. Wartości `unknown`, `unavailable`, błędne jednostki i pomiar z powtórzonej godziny zmiany czasu, gdzie długość danych przekracza zwykłą godzinę, są pomijane. Brak danych nie oznacza zerowego zużycia.
- Przechowywane są energia pompy (kWh) oraz średnia temperatura zewnętrzna wyliczana jako stopniogodziny dzielone przez pokrycie czasu. System nie zapisuje informacji o osobach ani o sterowaniu termostatem.

## Uczenie i ocena jakości

Model dzieli temperaturę na zakresy: poniżej −10°C, −10…−5, −5…0, 0…5, 5…10, 10…15, 15…25, powyżej 25°C. Każdy zakres wymaga **minimum 6 kompletnych godzin z co najmniej trzech różnych dni**.

Do wyświetlenia gotowego podglądu wymagamy:

- co najmniej **7 kompletnych dni** (minimum 20 zgodnych godzin dziennie),
- łącznie **minimum 48 poprawnych godzin**,
- **minimum dwóch wyuczonych zakresów temperatur**.

W każdym zakresie obliczamy medianę (P50) i 90. percentyl (P90) **średniej elektrycznej mocy pobieranej przez pompę**. Model nie wyznacza COP ani energii cieplnej — do tego potrzebne byłyby osobne pomiary ciepła.

Aby sprawdzić jakość, dla każdej starszej godziny testujemy model uczony **wyłącznie na wcześniejszych dniach**. Jeżeli nie ma wystarczająco wcześniejszych danych w danym zakresie, godzina nie jest oceniana. Wskaźniki MAE (kWh na godzinę) i średniego odchylenia są wstępne, dopóki nie zbierzemy co najmniej 12 testowanych godzin w przynajmniej 3 odrębnych dniach.

## Co zobaczysz w Home Assistant

Nowe sensory na urządzeniu ESTADI Energy Pilot:

| Sensor | Znaczenie |
|---|---|
| Pompa — stan uczenia temperatury | `zbieranie_temperatury_i_energii` / `gotowy_podglad` |
| Pompa — kompletne dni pomiarów temperatury | Postęp danych |
| Pompa — godziny sparowane z temperaturą | Liczba zgodnych godzin |
| Pompa — wyuczone zakresy temperatury | Liczba wytrenowanych zakresów |
| Pompa — błąd prognozy poboru | MAE kWh/h, obliczone na późniejszych dniach |
| Pompa — stan porównania 48h | Czy pogoda i wyuczone zakresy wystarczają |
| Pompa — model wyuczony 48h | Prognozowana energia w porównywalnych godzinach |
| Pompa — dotychczasowy model 48h | Energia według starego wzoru w tych **samych godzinach** |
| Pompa — różnica prognozy 48h | Różnica nowy minus stary model, kWh |

W atrybutach **Pompa — stan uczenia temperatury** znajdziesz wyuczone temperatury, P50/P90, liczbę próbek, ocenę na historycznych dniach oraz dostępność czujników.

**Prognozy 48h są porównywane wyłącznie dla godzin, w których znamy temperaturę przyszłą i mamy wyuczony zakres.** Jeżeli będzie to np. 12 godzin, pokażemy porównanie za 12 godzin, a nie fikcyjne 48.

## Nowy pulpit

Eksport nowego YAML pełnego pulpitu dodaje sekcję **„Pompa ciepła — uczenie z temperatury”**, w tym tabelę z zakresami temperatur, mocą typową/P90 oraz porównaniem energii prognozowanej przez stary i nowy model.

Po aktualizacji naciśnij ponownie przycisk **„Wygeneruj pulpit, miniwidżet i wykres 48h”**. Nie nadpisujemy poprzednich plików — nowy eksport powstanie jako osobny YAML. Zasób wykresu JS nie zmienił się w tej wersji.

## Dlaczego modelu nie włączamy od razu do planowania?

Rzeczywisty pobór pompy zależy również od podgrzewania CWU, odszraniania, harmonogramu pracy sprężarki, nastaw termostatów i taryfy. Korelacja z temperaturą sama w sobie nie gwarantuje dokładności.

Dlatego wersja 0.4.3 pokazuje **porównanie wyuczonego modelu z dotychczasowym**, ale **nie zmienia automatycznie planu ładowania magazynu**, nie zastępuje funkcji `pump_power_w` w istniejących scenariuszach ekonomicznych i nie steruje pompą/Deye. W przyszłości należy sprawdzić jakość na różnych porach roku i dopiero osobną decyzją przełączyć model, z możliwością cofnięcia.

## Testy

Nowe testy w `tests/test_heat_pump_learning.py` weryfikują: integrację pomiarów temperatury, brak uzupełniania braków zerem, brak retrospektywnego uzupełnienia historii, próg siedmiu dni, wymaganie kilku temperatur, ocenę na wcześniejszych dniach, odrzucenie godzin o niepełnym pokryciu oraz prognozy z ograniczonym zasięgiem pogody. Pozostałe testy projektu i walidacja Home Assistanta pozostają wymagane przed scaleniem do `main`.
