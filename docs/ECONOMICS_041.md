# ESTADI Energy Pilot v0.4.1 — porównanie kosztów 48 godzin

## Co dokładnie porównuje system?

Silnik `scenario_economics.py` wykonuje **dwa niezależne przebiegi po 192 przedziały 15 minut**, na tych samych danych i tych samych ograniczeniach magazynu:

1. **Bez dodatkowego ładowania magazynu z sieci** — energia PV zasila dom, a nadwyżka magazyn; przy niedoborze bateria może zasilać dom aż do minimalnego SOC.
2. **Z proponowanym planem taniego ładowania** — to samo PV, dom, pompa i EV, ale w proponowanym oknie G12w/G13 magazyn może dodatkowo pobierać energię z sieci, maksymalnie do ustalonego celu SOC i z ograniczeniem importu (np. przyłącze 15 kW minus bufor 2 kW).

Silnik respektuje pojemność nominalną magazynu (28 kWh), rzeczywisty SoH z opcji, min/max SOC, maksymalną moc ładowania, sprawność obustronną, taryfę i brak możliwości jednoczesnego rozładowania baterii do domu podczas jej planowanego ładowania z sieci. Zakłada to samo zachowanie PV i odbiorników w obu scenariuszach, żeby porównanie było sensowne.

**Deye Load zawiera cały dom, EV i pompę ciepła.** Model korzysta z profilu bazowego *po wyłączeniu EV i pompy*; prognozę pompy dodaje dokładnie raz. Aktualny pomiar EV jest uwzględniony tylko na pierwsze 15 minut, ponieważ przyszłego harmonogramu ładowania EV jeszcze nie znamy. Uwaga: ten model **nie nadaje się do natychmiastowej ochrony przyłącza**.

## Ceny energii

W **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → Konfiguruj → Zaawansowane** ustaw:

- **G12w / G13:** stawki poboru energii w odpowiednich strefach w zł/kWh, z rzeczywistej taryfy i rachunku, uwzględniając zmienne koszty dystrybucji. Nie wpisuj przypadkowych przykładowych cen.
- **Szacunkowa wartość energii oddanej do sieci (zł/kWh):** osobna kwota do modelu; domyślnie **0 oznacza brak potwierdzonej wartości**, nie darmowy eksport. Ustaw dopiero, gdy wiesz, w jaki sposób rozliczany jest Twój depozyt prosumencki. Tu podawana wartość jest *uproszczoną średnią* — nie zastępuje rozliczeń godzinowych, RCEm, współczynników ani ograniczeń depozytu.

Jeśli brakuje stawek importu, koszty i różnice w PLN są **nieznane**. Jeśli nie podano wartości eksportu, system może wyświetlić różnicę kosztów **samego importu**, ale nie wynik netto uwzględniający eksport.

## Dlaczego końcowy SOC ma znaczenie?

Załóżmy, że po 48h:

- scenariusz A pozostawia **10% SOC** i koszt importu **15 zł**;
- scenariusz B pozostawia **40% SOC** i koszt importu **20 zł**.

To **nie znaczy**, że scenariusz A oszczędza 5 zł. W B zostało znacznie więcej energii w magazynie — należy ją uwzględnić, zanim porównanie uznamy za uczciwe.

Dlatego silnik pokazuje **końcowy SOC obu wariantów** i jego różnicę. Pole `porównywalna różnica salda` pozostaje puste, gdy różnica przekracza **0,5 punktu procentowego**. Gdy SOC jest podobny i ceny importu oraz eksportu są dostępne, oblicza jedynie **wstępną różnicę salda zakupu minus szacunkowe uznanie eksportu**. To nadal **nie są oszczędności zrealizowane**, tylko prognoza dwóch scenariuszy przy założonych warunkach.

Wynik `oszczednosci_pln` i `realized_savings_pln` pozostaje **None** — brak weryfikacji faktycznego sterowania i rzeczywistych warunków net-billingu.

## Nowe sensory

Na urządzeniu Home Assistant zobaczysz:

| Sensor | Jednostka |
|---|---|
| Opłacalność 48h — status | Informacja o danych i ograniczeniach |
| Opłacalność — import bez dodatkowego ładowania | PLN |
| Opłacalność — import z planowanym ładowaniem | PLN |
| Opłacalność — różnica kosztu importu | PLN |
| Opłacalność — eksport bez ładowania | kWh |
| Opłacalność — eksport z ładowaniem | kWh |
| Opłacalność — końcowy SOC bez ładowania | % |
| Opłacalność — końcowy SOC z ładowaniem | % |
| Opłacalność — różnica końcowego SOC | p.p. |
| Opłacalność — porównywalna różnica salda | PLN (tylko przy spełnionych warunkach) |

Atrybuty **Opłacalność 48h — status** zawierają szczegóły obu scenariuszy, prognozowany import, eksport, chwilowe limity i tabelę 4-godzinnych sum. Dodatkowy blok pojawia się w eksportowanym pulpicie z wersji 0.4.0; aby go zobaczyć, **naciśnij ponownie przycisk eksportu i zaimportuj nowy plik YAML**. Istniejący pulpit i jego zmiany nie są nadpisywane.

## Ograniczenia aktualnej wersji

- Prognoza wprowadzona w 0.4.1 **nie wysyła poleceń Deye ani ładowarce EV**.
- Planista proponuje moc i czas startu jedynie na podstawie uproszczonego modelu, a nie potwierdzonej reakcji BMS/TOU w Twoim falowniku.
- Nieznane przyszłe sesje EV, odszranianie pompy i niepewna produkcja PV mogą istotnie zmienić prawdziwy rachunek.
- Przy braku prognozy PV w godzinach nasłonecznienia **nie pokazuje kosztu pełnych 48 godzin**. W nocy brak PV traktowany jest jako konserwatywne zero i jawnie zliczany.
- Przyłącze 15 kW ogranicza hipotetyczne dodatkowe ładowanie, ale jeżeli sam dom przekroczy limit, symulator **raportuje problem**, nie zabezpiecza fizycznie instalacji.
- G13 wymaga rzeczywiście obowiązujących u Twojego sprzedawcy godzin i stawek; nie należy przenosić cennika G12w na G13.
- Wskaźnik „bilans po eksporcie” to **uproszczona prognoza** (import według stref minus eksport razy podana cena), a nie pełna faktura prosumencka.

## Testy

Zestaw testów obejmuje oba modele magazynu, brak stawek i eksportu, różny SOC końcowy, ograniczenie 13 kW, samochód EV uwzględniony jeden raz, nadwyżki PV, niepełną prognozę, DST, złe dane planu i zakaz traktowania wyniku jako zrealizowanej oszczędności.
