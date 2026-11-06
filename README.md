# ESTADI Energy Pilot — wersja 0.4.2 (beta)

**Własna integracja Home Assistant (HACS) do prognozowania ładowania magazynu energii i oceny trafności prognoz.** Wersja **doradcza**: odczytuje sensory, oblicza cele SOC, ale **nie steruje falownikiem Deye**.

## Instalacja przez HACS — bez kopiowania plików

1. W Home Assistant otwórz **HACS → Integracje**.
2. Otwórz menu (trzy kropki) i wybierz **Własne repozytoria / Custom repositories**.
3. Wklej adres: **https://github.com/endigarnek/estadi-energy-pilot**
4. Jako typ wybierz **Integracja / Integration** i zatwierdź.
5. Znajdź **ESTADI Energy Pilot**, kliknij **Pobierz / Download**, a następnie (jeżeli pojawi się taki komunikat) **uruchom ponownie Home Assistant**.
6. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację**, wyszukaj **ESTADI Energy Pilot**.
7. Wskaż sensory Solcast na dziś i jutro, stan baterii (%), temperaturę zewnętrzną, opcjonalnie prognozę pogody. Wprowadź **użyteczną** pojemność baterii (kWh) i średnią moc domu **bez pompy** (W).

HACS może pobierać zawartość domyślnej gałęzi repozytorium także bez wydania GitHub Release. Jeśli nie masz HACS, najpierw trzeba zainstalować sam HACS. Można również wgrać ręcznie folder `custom_components/estadi_energy_pilot` do `/config/custom_components/` i zrestartować HA.

## Co oblicza

- **Solcast**: szczegółowa półgodzinna (lub godzinowa) prognoza produkcji dla wybranych dni.
- **Pompa ciepła**: przy temperaturze od +8°C w górę przyjęte 0 W, tuż poniżej +8°C ok. 600 W, przy -5°C i niższych ok. 1200 W (wartości konfigurowalne). Są to **założenia**, a nie odczyty z licznika.
- Dwa osobne cele **SOC**: na koniec nocnej strefy taniej (domyślnie 07:00, energia do 13:00) oraz na koniec popołudniowej (16:00, energia do 21:00).
- Uwzględnia rezerwę SOC, margines 1 kWh, redukcję prognozy PV ze względu na ryzyko i przybliżoną sprawność energetyczną.
- Czujniki celu SOC, prognozy PV, zużycia oraz ilości kWh do doładowania w bieżącym tanim oknie. Odświeżanie co 15 minut.

**Ważne:** integracja nie ma jeszcze dopracowanego interfejsu z wykresem ani własnego automatycznego uczenia się. Jest to MVP do sprawdzenia obliczeń na Twojej instalacji, nie gotowy sterownik.

## Solcast — opcjonalne źródło zapasowe

Jeżeli wybierasz alternatywny Solcast zamiast zainstalowanego Forecast.Solar, integracja współpracuje z [BJReplay/ha-solcast-solar](https://github.com/BJReplay/ha-solcast-solar). W jej konfiguracji włącz szczegółowe atrybuty **detailedForecast** (lub **detailedHourly**) dziennych sensorów `Forecast Today` oraz `Forecast Tomorrow`. Jeżeli brak szczegółowych danych, nasza integracja zasygnalizuje brak prognozy i nie wyliczy celu SOC.

Dla każdej pozycji `pv_estimate` oznacza średnią **moc w kW** przez okres, a nie kWh.

## Konfiguracja i bezpieczeństwo

Ustawienia można później zmienić: **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → Konfiguruj**.

- Nie podłączaj automatycznego zapisu celu SOC do falownika na podstawie tego prototypu.
- Zweryfikuj wyliczenia na kilku dniach rzeczywistych danych przed rozważaniem sterowania.
- Sprawdź godziny tanich taryf w umowie i popraw parametry w integracji; ustawienia domyślne (21–07, 13–16) są przykładowe.
- Model nie obejmuje CWU, odmrażania, aut elektrycznych, indywidualnego harmonogramu pompy ani cen energii.
- Brak aktualnej prognozy lub pomiarów uniemożliwia wyliczenie zalecanego ładowania.



## Wersja beta 0.3.0 — pierwszy działający etap 2.0

Obsługiwane teraz: pojemność 28 kWh nominalnie (SOC 10–100%), suwaki pojemności i korekty zapasu, kalendarz G12w/G13, podgląd przyłącza 15 kW, wstępna rekomendacja startu i mocy ładowania oraz wyjaśnienia. **Nie włącza automatycznego sterowania Deye.** Najpierw trzeba potwierdzić znaki mocy importu i ładowania, pomiary faz i limity falownika.

**[Instrukcja aktualizacji, kalibracji i ograniczenia bety](docs/EP20_BETA_03.md)** · **[Miniwidżet na pulpit Home Assistant](docs/MINI_WIDGET_03.md)**.

## Wersja 0.4.2 — kalibracja prognoz na historii i ryzyko przyszłego EV

**Nowy moduł kalibracji** ocenia dotychczasowy profil domu na wcześniejszych dniach pomiarów (bez korzystania z danych ocenianego dnia). Oblicza błąd MAE i WAPE zużycia bazowego po odjęciu **EV i pompy**, które są już wliczone do Deye Load. Godziny z niepełnymi albo sprzecznymi pomiarami są odrzucane zamiast zastępowane zerami.

**Korekta PV**: po 7 dniach z kompletną historią i zamrożoną poprzedniego wieczoru prognozą moduł wylicza sugerowany **całkowity procent ostrożnej korekty PV (0–40%)**. Sugestii nie stosuje automatycznie.

**Nowy wariant niepewnego EV**: gdy są przynajmniej 7 kompletnych dni pomiaru (w tym 3 robocze i 3 wolne), liczy osobne godzinowe P90 energii samochodu, a następnie **osobno** sprawdza obie strategie ekonomiczne z takim historycznym obciążeniem. Pierwszy kwadrans pozostaje pomiarem bieżącej ładowarki. Wariant P90 to scenariusz stresowy, **nie pewny harmonogram ani prawdopodobieństwo**. Nie zmienia podstawowego planu i nie wysyła poleceń do Deye/EV.

Dodano 10 sensorów z przedrostkami **Kalibracja**, **EV — stan historycznego scenariusza** i **Opłacalność — ... z ryzykiem EV**, ich szczegółowe atrybuty oraz dwie sekcje pulpitu. Aby odświeżyć dashboard, ponownie wygeneruj jego YAML i zaimportuj nowy plik. Nie są nadpisywane wcześniejsze pliki.

**[Instrukcja kalibracji i interpretacji ryzyka EV](docs/CALIBRATION_EV_042.md)**. Zrealizowane oszczędności w PLN pozostają nieznane; pełna kontrola faz i BMS oraz sprzętowe sterowanie Deye nadal niewłączone.

## Wersja 0.4.1 — uczciwe porównanie kosztów pracy magazynu

Nowy symulator `scenario_economics.py` porównuje **dwa pełne scenariusze 48h co 15 minut**: działanie magazynu bez dodatkowego ładowania z sieci oraz działanie z **proponowanym** tanim ładowaniem (G12w/G13). Oba warianty korzystają z tej samej prognozy PV, profilu domu bez EV/pompy, prognozy pompy, SOC i sprawności magazynu, limitu 15 kW i bufora mocy.

W obu wariantach liczymy import/eksport w kWh, koszt zakupu w PLN (tylko z rzeczywistych wpisanych taryf), szacowaną wartość eksportu, końcowy SOC i różnice. **Gdy końcowy SOC się różni, nie pokazujemy tego jako porównywalnej oszczędności**. Przy podobnym SOC (do 0,5 p.p.) i kompletnych cenach wyświetlana jest wyłącznie **wstępna różnica salda scenariuszy**, nie realny zysk. Zrealizowane oszczędności pozostają nieznane.

W **Opcjach zaawansowanych** pojawiło się pole `Szacunkowa wartość energii oddanej do sieci (zł/kWh)`, z ustawieniem **0 = nieznana**. Nie wpisujemy automatycznie ani cenników TAURON, ani stawek RCEm. Nie jest to pełne rozliczenie net-billingu.

W Home Assistant dostępnych jest 10 sensorów z przedrostkiem **Opłacalność**. Do pełnego pulpitu dołączono tabelę z porównaniem dwóch wariantów — wystarczy ponownie użyć przycisku eksportu z wersji 0.4.0 (tworzy nowy plik, nie nadpisuje edytowanego).

**[Instrukcja, przykład i interpretacja wyników](docs/ECONOMICS_041.md)**.

**Bezpieczeństwo:** nie dodano żadnych komend Deye ani EV; wymagana jest nadal weryfikacja rzeczywistego BMS, faz i prognozy przyszłych sesji EV.

## Wersja 0.4.0 — interaktywny wykres prognozy 48h na pulpicie

Do pełnego pulpitu z 0.3.9 dodano nową, niezależną od zewnętrznych bibliotek **kartę Lovelace z wykresem SVG**. Na jednej osi czasu pokazuje **SOC baterii**, PV, cały dom z Deye Load, import/eksport, pompę ciepła i samochód EV, a tło oznacza tanie strefy taryf G12w/G13. Na telefonie można dotknąć godzinę, na desktopie wskazać myszą, a z klawiatury poruszać się strzałkami. Poszczególne serie można ukrywać. **SOC jest w %, pozostałe serie oznaczają kWh w godzinie, nie chwilowe kW.**

Eksporter z przycisku **„Wygeneruj pulpit, miniwidżet i wykres 48h”** przygotowuje 3 pliki: `estadi-energy-pilot-dashboard.yaml`, `estadi-energy-pilot-mini.yaml` oraz `www/estadi-energy-pilot-forecast-v040.js`. Nie nadpisuje istniejących eksportów. ID sensora symulacji pobiera automatycznie z Entity Registry.

**Wymagany jeden dodatkowy krok:** w Home Assistant → Ustawienia → Pulpity → Zasoby dodaj `/local/estadi-energy-pilot-forecast-v040.js` jako **Moduł JavaScript**, zanim wkleisz nowy dashboard. Nie jest potrzebna żadna dodatkowa integracja HACS ani zewnętrzny serwer. Pozostawiono także zapasową, natywną tabelę danych na wypadek niedostępności karty.

**[Instrukcja instalacji karty i obsługi wykresu](docs/FORECAST_CARD_040.md)**.

**Ograniczenia pozostają jawne:** przyszłe sesje EV są nieznane; silnik nadal pokazuje scenariusz bez dodatkowego ładowania z sieci, a nie wykonanie planu Deye; przy niepełnej prognozie wykres nie tworzy sztucznych wartości. **Nie uruchamia sterowania** i nie zastępuje ochrony 15 kW ani limitów BMS.

## Wersja 0.3.9 — pełny pulpit energii i miniwidżet HA

**Nowy przycisk na urządzeniu: „Wygeneruj pulpit i miniwidżet YAML”.** Po kliknięciu zapisuje do `/config` dwie gotowe konfiguracje Lovelace: `estadi-energy-pilot-dashboard.yaml` i `estadi-energy-pilot-mini.yaml`. Nazwy encji są pobierane z **prawdziwego rejestru Home Assistanta**, a nie zgadywane z polskich nazw. Przycisk niczego nie zmienia w istniejących pulpitach i nie nadpisuje wcześniejszych eksportów.

Pełny pulpit zawiera podsumowanie **SOC / PV / Deye Load / EV / pompy**, natywne wykresy historii 24h, plan taniego ładowania, Grid Guard, status TOU Deye, historię dry-run i dokładność prognoz. Prognoza przyszłego SOC na 48h jest na razie czytelną **tabelą co 4 godziny** — standardowa karta HA History Graph przedstawia tylko historię i nie potrafi natywnie narysować przyszłej prognozy. Miniwidżet prezentuje najważniejsze pomiary i decyzję.

**[Instrukcja: wygeneruj i zaimportuj gotowe pulpity](docs/DASHBOARD_039.md)**. Do wyświetlania wystarczają standardowe karty Home Assistanta; nie trzeba doinstalowywać ApexCharts ani Mushroom. Przygotowane pliki trzeba jednorazowo wkleić do **nowego pustego pulpitu → Edytor konfiguracji surowej**. Automatyczne tworzenie pulpitów HA nie jest jeszcze wdrożone. Nie jest to też automatyczne sterowanie falownikiem.

## Wersja 0.3.8 — rzeczywista weryfikacja prognoz i celu SOC

Wprowadzono **kontrolę prognoz w czasie**, bez przepisywania wcześniejszych przewidywań po poznaniu wyniku.

1. Co najmniej co 6 godzin, gdy symulator ma pełne 48 godzin danych, system **zamraża prognozowany SOC na +3, +6, +12 i +24 godziny**. Każdą migawkę zapisuje osobno z czasem i jakością modelu. Nie zmienia jej przy kolejnych aktualizacjach pogody.
2. W chwili docelowej porównuje zamrożoną prognozę z **rzeczywistym odczytem SOC Deye**. Odczyt musi mieć jednostkę `%`, poprawny znacznik czasu i być nie starszy niż 30 minut. Pomiar spóźniony o ponad 45 minut jest oznaczony jako `brak_odczytu`, a nie sztuczne zero.
3. Wyniki pokazują odchylenie w punktach procentowych i **MAE** (średnią bezwzględną różnicę) osobno dla horyzontów 3/6/12/24h.
4. Niezależnie rejestruje jeden **docelowy SOC na koniec danego taniego okna** i oznacza, czy rzeczywiście go osiągnięto. Jest to jedynie zaobserwowany stan — **nie** wykonanie planu przez integrację, ponieważ automatyka nadal jest wyłączona.
5. Weryfikuje również **PV dzień wcześniej vs rzeczywisty pomiar** z istniejących migawek Forecast.Solar / Solcast (zamrożonych wieczorem). Liczy dni porównywalne, MAE w kWh, WAPE w procentach i średnie odchylenie `prognoza - rzeczywistość`. Niepełne dni są wykluczane.
6. Wyniki i migawki są zachowywane w osobnym lokalnym magazynie HA do 14 dni (maks. 240 zapisów). Restart nie resetuje historii porównań.

**Nowe sensory:** `Weryfikacja prognoz — stan`, `Weryfikacja — odchylenie SOC 3h/6h/12h/24h`, `Weryfikacja — błąd PV WAPE`, `Weryfikacja — porównane dni PV`, `Weryfikacja — cele SOC osiągnięte` i `nieosiągnięte`. Szczegóły ostatnich 12 prognoz i pomiarów są w atrybutach statusu.

### Jak interpretować liczby

- **MAE SOC 3h = 4 p.p.** oznacza, że dotychczasowe *obserwowane odchylenie* scenariusza na trzy godziny wynosiło średnio 4 punkty procentowe. Póki model opiera się na mniej niż siedmiu porównaniach, metryka jest wstępna.
- **WAPE PV = 20%** oznacza sumę bezwzględnych błędów prognozy podzieloną przez sumę *rzeczywistej produkcji PV* w dniach porównywalnych. Gdy produkcja wynosi blisko zero, wskaźnik jest nieokreślony.
- **Osiągnięty SOC** oznacza, że Deye rzeczywiście miał wymagany poziom energii na koniec wskazanego okna. Moduł nie sterował jego ładowaniem.
- **Ważne ograniczenie:** model SOC z wersji 0.3.3 przewiduje scenariusz **bez dodatkowego ładowania magazynu z sieci i bez przyszłych sesji EV**. Jeśli Deye rzeczywiście ładował magazyn z sieci, różnica pomiędzy przewidywaniem a wynikiem **nie jest** obiektywnym błędem algorytmu sterowania. Dopiero późniejsza kontrola rzeczywistych przepływów import/eksport i mocy baterii pozwoli oceniać czystość symulacji i liczyć rzeczywiste oszczędności.
- Moduł wciąż **nie podaje zrealizowanych oszczędności w PLN**, ponieważ nie mamy pewnego odtworzenia kontrfaktycznego scenariusza bez magazynu, kosztów eksportu/net-billingu i wykonywanych nastaw.

**Bezpieczeństwo:** nie dodano żadnych komend Deye ani EV; `automatyzacja_wlaczona: false`.

## Wersja 0.3.7 — dziennik decyzji i test dry-run (bez wysyłania komend)

Nowy **tryb testowy dry-run** pozwala przez 7 dni obserwować, jakie nastawy zaproponowałby ESTADI Energy Pilot, co zrobiłby po uruchomieniu EV albo pompy i dlaczego plan został ograniczony. Zapisuje lokalnie decyzje, ich przyczyny, bieżący import oraz hipotetyczną moc magazynu. Oddzielnie pokazuje **plan** i **blokady bezpieczeństwa**.

- Sensory: `Dry-run — stan testu`, `hipotetyczna decyzja`, `hipotetyczna moc magazynu`, `zapisane decyzje`, `kompletne dni testów`, `ostatnia decyzja o`.
- Archiwum: maksymalnie 8 dni / 1000 zdarzeń w lokalnym storage; 20 ostatnich zdarzeń w atrybutach statusu. Dzień uznajemy za kompletny po 80 **różnych** 15-minutowych pomiarach, a nie po 80 przypadkowych zmianach.
- Bieżący Grid Guard nadal odświeża się co 15 sekund, pełny plan co 15 minut. Hypotetyczne reakcje zapisują się przy zmianie decyzji.
- Poprawiono błąd wywołania `guard.allowed_charge_kw` na słowniku — w niektórych przypadkach powodował nieudany pełny plan.
- **Zero wysyłanych poleceń do Deye/EV**, nawet jeśli zebrano pełne 7 dni. Wymagane są nadal L1/L2/L3, potwierdzenie BMS, modelu/TOU i test sprzętowy.

**[Instrukcja i interpretacja dry-run 0.3.7](docs/DRY_RUN_037.md).**

## Wersja 0.3.6 — odczyt sześciu programów Deye TOU bez sterowania

Kolejny etap przygotowań do automatyzacji: integracja **automatycznie rozpoznaje encje Home Assistant opisujące sześć programów Time of Use falownika Deye**. Pokazuje czas rozpoczęcia, SOC, moc i tryb ładowania każdego programu; niejednoznaczne/brakujące pola zgłasza jako problem, zamiast zgadywać.

**Nowe sensory**: `Deye TOU — stan rozpoznania`, `poprawnie odczytane pola`, `data migawki ustawień`, `zmiany od migawki`, `gotowość do automatyzacji`. W atrybutach statusu widać wszystkie sześć programów i listę konkretnych blokad.

Przy **pierwszym kompletnym odczycie** powstaje lokalna kopia wartości TOU (w `.storage`). Kolejne odczyty — przy pełnym planowaniu i po odświeżeniu Grid Guard co 15 sekund — pokazują różnice względem tej kopii. Kopia nie umożliwia jeszcze automatycznego przywracania; nie jest do tego używana.

Moduł **nie wysyła żadnej komendy do Deye ani EV**. Nawet kompletny odczyt nie oznacza gotowości do automatyzacji: wymagane są pomiary faz, identyfikacja sprzętu i kontrolowany test zapisu/odczytu zwrotnego z procedurą przywrócenia.

**[Instrukcja interpretacji odczytu Deye i wymagane kroki](docs/DEYE_TOU_DIAGNOSTYKA_036.md)**.

## Wersja 0.3.5 — Grid Guard LIVE i diagnostyka L1/L2/L3

**Szybki monitoring przyłącza, ale nadal bez sterowania Deye.**

- Niezależny od planisty odczyt mocy sieci, baterii i opcjonalnych prądów/napięć L1/L2/L3 **co 15 sekund**. Nie wywołuje Forecast.Solar ani przeliczania 48h, nie zwiększa obciążenia falownika żadnymi zapisami.
- Weryfikacja źródła: jednostka W/kW, A, V; ostatnia raportowana zmiana/odczyt; dane starsze niż **120 sekund** są odrzucane. Brak danych nie jest zerem.
- Opcjonalny **limit prądu osobno na każdą fazę**, z warunków przyłączenia/rozdzielnicy. Domyślnie **0 A = niepotwierdzony**, więc brak fałszywej zgody na regulowanie baterią. Sensory fazowe i limity ustawia się w zaawansowanej konfiguracji. Nie wpisuj wartości „na oko”.
- Grid Guard rozlicza rzeczywisty pomiar **importu z sieci** (Deye Grid) zawierający EV, pompę i już pracujące ładowanie baterii; nie dodaje żadnej z tych mocy ponownie. Po wyłączeniu auta nowy odczyt może podnieść wyliczony pułap ładowania magazynu, ale **nie zmienia nastaw falownika**.
- Widoczne sensory: **Grid Guard — kontrola faz**, **ostatni odczyt**, **moc ładowania magazynu**. Atrybuty sensora **Grid Guard — status** zawierają stan każdego źródła (`ok`, `dane_nieaktualne`, `bledna_jednostka`, `brak_encji`), wiek odczytu i to, czy ustawiono rzeczywiste limity faz.
- Przyłącze użytkownika **15 kW** i bufor **2 kW** pozostają parametrami modelu. Szybszy odczyt **nie jest zabezpieczeniem nadprądowym**: Home Assistant, Modbus i Deye mogą mieć opóźnienia, a obciążenie pojedynczej fazy może być niebezpieczne mimo prawidłowej sumy kW.

**Ważne:** jeżeli wciąż nieznany jest znak pomiaru importu lub ładowania baterii, `Grid Guard` świadomie pozostaje w stanie `blokada`. Trzeba potwierdzić bieżący znak rzeczywistym pomiarem, a nie zmieniać opcji na chybił trafił. Gdy trzy fazy są poprawnie odczytane, widnieje status `pomiar_3_faz`, ale `automatic_ready` pozostaje **false** — nie zweryfikowano jeszcze mapy Deye, sprzętowej ochrony faz ani BMS.

**Testy i kolejne kroki:** testy odmowy przy starych/błędnych sensorach, działania EV 11kW, stopniowego odzyskania zapasu i ograniczenia pojedynczej fazy; następnie analiza sprzętowej reakcji Deye, pełny dry-run i dopiero osobny przełącznik automatyzacji.

## Wersja 0.3.4 — dobór godziny rozpoczęcia i mocy ładowania magazynu

Wprowadzono **drugą, niezależną symulację**: 15-minutowy doradca ładowania w nadchodzącym oknie taniej taryfy G12w/G13. Wyznacza najlepszy wykonalny wariant `godzina startu`, `moc kW`, `cel SOC`, `energia do pobrania z sieci`, `przewidywany koniec`, a także do czterech alternatyw.

**Jak liczy:**
- 28 kWh nominalnie (edytowalne), SOC min 10%, maks. 100% oraz korekta SOC użytkownika zastosowana **raz** w istniejącym modelu.
- Realna długość taniego okna (np. G12w w dni robocze 13–15, a nie 13–16); rezerwa 15 min przed końcem, sloty co 15 minut, obsługa zmian DST.
- Preferowana moc 5 kW, kandydaci od 3 kW do zadanego maks. limitu baterii. Symuluje PV, profil domu bez EV i bez pompy (z historii), osobny pobór pompy oraz EV.
- **15 kW przyłącza**, z konfigurowalnym buforem (np. 2 kW → limit roboczy 13 kW). Import nie jest obliczany przez ponowne dodawanie już zliczonych odbiorników.
- **Ważna ostrożność wobec EV:** jeśli samochód ładuje się w chwili odświeżenia, model zakłada, że może pobierać tę moc przez całe tanie okno. Gdy EV przestanie ładować, nowe przeliczenie może zwiększyć zalecaną moc magazynu. Nie znamy z góry harmonogramu EV. Przeliczenia nadal odbywają się co 15 minut — to NIE jest układ szybkiego zabezpieczenia przyłącza.
- PV jest kierowane najpierw do domu, potem do magazynu. Gdy w magazynie ma trwać ładowanie z sieci, model nie zakłada jego jednoczesnego rozładowywania do domu. Odmowa brakujących prognoz PV w godzinach potencjalnej produkcji; nieosiągalny SOC pokazuje szacowany pułap zamiast fałszywego planu.
- Proponowany harmonogram jest **warunkowy i tylko doradczy**, ponieważ nie zweryfikowano jeszcze pomiarów/prądów wszystkich faz, dopuszczalnej mocy BMS ani skuteczności komend falownika Deye. **Nie wysyła jakichkolwiek poleceń do Deye ani ładowarki EV**.

**Nowe sensory** Home Assistant: `Inteligentne ładowanie — stan`, `proponowana moc`, `godzina startu`, `przewidywany koniec`, `cel SOC`, `energia z sieci`, `szczyt poboru`. W atrybutach `Inteligentne ładowanie — stan` zobaczysz przyczynę decyzji oraz do 4 alternatywnych planów.

**Rozgraniczenie wyników:** istniejąca `Symulacja 48h — stan` pokazuje scenariusz bez dodatkowego ładowania z sieci. `Inteligentne ładowanie` symuluje inne zachowanie baterii w najbliższym tanim oknie. Nie porównuj ich bezpośrednio jako dwóch prognoz *tego samego harmonogramu*; pełne porównanie opłacalności wymaga jeszcze wspólnego bilansu 48h, rzeczywistych cen importu/eksportu i historii EV.

Po aktualizacji do **0.3.4** uruchom ponownie Home Assistant. Sprawdź **Wersja integracji** i sensory z przedrostkiem **Inteligentne ładowanie**. Komunikaty `nieosiagalny` / `brak_prognozy_pv` / `brak_celu` oznaczają brak warunków do wiarygodnego zalecenia, a nie błąd instalacji.

## Wersja 0.3.3 — symulacja magazynu SOC na 48 godzin

Pierwszy działający **symulator przepływów energii krok po kroku** (co 15 minut, maks. 192 kroki). Wykorzystuje już podłączone sensory Deye, prognozę godzinową Forecast.Solar, prognozę temperatury Met.no, rozdzielony profil domu **bez EV i bez pompy** (P50/P90 z 7–30 dni), pojemność nominalną 28 kWh / SoH, SOC min 10% i max 100%, sprawność oraz kalendarz G12w/G13.

**Co oblicza:**
- PV → bezpośrednie zasilenie domu → nadwyżka do baterii (z limitem mocy i miejsca) → eksport.
- Gdy brak PV, bateria zasila dom do **minimalnego SOC**, po czym prognozowany import z sieci wzrasta; energia nie jest pożyczana z późniejszego słońca.
- Energię importowaną, eksportowaną, produkcję PV, pobór domu, pompy i EV, SOC na początku/końcu godziny, minimum SOC oraz ostrzeżenie o szczycie importu powyżej przyłącza.
- Dwa scenariusze: `typowy` (profil P50) oraz `ostrożny` (P90); zanim powstanie profil, bazuje na ręcznej mocy domu i flaguje jako `wstępny`.
- Prognozowany koszt samego **importu** w PLN, ale wyłącznie po wpisaniu cen brutto/kWh dla wszystkich stref. **Oszczędności netto** pozostają nieznane dopóki nie uwzględnimy eksportu/net-billingu i obecnego harmonogramu magazynu.

**Nowe sensory** na urządzeniu: `Symulacja 48h — stan`, `wiarygodność`, `dostępne godziny`, `SOC końcowy`, `minimalny SOC`, `minimalny SOC ostrożny`, `import z sieci`, `produkcja PV`, `zużycie domu`, `szczyt importu`, `koszt importu`. W atrybutach sensora **Symulacja 48h — stan** jest `harmonogram_48h` z maksymalnie 48 punktami godzinowymi, wygodnymi do późniejszego wykresu. Obliczenia wewnętrzne pozostają 15-minutowe.

**Świadome ograniczenia bezpieczeństwa tego etapu:**
1. Symulacja pokazuje scenariusz **bez dodatkowego ładowania baterii z sieci**. Obecny prosty doradca ładowania jest oddzielny; bez potwierdzonych pomiarów nie łączymy obu wyników w jedną rzekomo kompletną automatykę.
2. Bieżące ładowanie EV jest uwzględnione tylko przez pierwsze 15 minut. Przyszłych sesji samochodu nie da się przewidzieć z jednego pomiaru; bez harmonogramu nie wolno ich wymyślać. Wyniki przyszłego importu mogą więc być zaniżone podczas długiej sesji EV.
3. Jeżeli prognoza PV na dzień urywa się, wynik ma status **niepełna prognoza PV**, a nie „gotowy plan na 48h”. Brakujące dane pogodowe zastępuje aktualna temperatura, z niższą wiarygodnością.
4. Model mocy pompy nadal jest uproszczeniem temperatury; rzeczywiste skoki CWU/odszraniania wymagają historii pomiarów Shelly.
5. Sprawność modelowana jest uproszczonym wspólnym współczynnikiem. Limit importu 15 kW ma status alarmu w symulacji, **nie steruje przyłączem** i nie sprawdza jeszcze faz L1/L2/L3.
6. Niczego nie zapisuje w Deye. Sterowanie automatyczne pozostaje **wyłączone**.

Instalacja: zaktualizuj istniejącą integrację do **0.3.3** przez Marketplace/HACS, uruchom ponownie HA. W sensorze **Symulacja 48h — stan** sprawdź `status`, `przyczyna`, `harmonogram_48h` i prognozę ostrożną. Porównuj to z kolejnymi dniami rzeczywistych pomiarów. Nie przełączaj automatycznie Deye na podstawie wstępnych wyników.

## Wersja 0.3.2 — potwierdzona instalacja: Deye Load zawiera cały dom

**Potwierdzono wprost:** `sensor.deye_load_power` obejmuje wszystkie odbiorniki domu, w tym **samochód EV i pompę ciepła**. Integracja przy pierwszym uruchomieniu po aktualizacji migruje wcześniejszy wybór `unknown` do **EV wliczone w Deye Load** (bez ponownego ustawiania encji). Jeżeli użytkownik kiedykolwiek fizycznie zmieni podłączenie i świadomie ustawi `excluded`, ta decyzja jest zachowywana.

W encji **Uczenie zużycia domu** otrzymujemy dwa rozdzielone godzinowe profile:

- **Dom bez EV, z pompą ciepła**: `Deye Load − EV`. Użyteczny do obrazu faktycznego zużycia domu bez ładowania auta.
- **Dom bazowy bez EV i bez pompy**: `Deye Load − EV − moc pompy`. Ten profil może w przyszłości zostać zsumowany z *osobną* prognozą pracy pompy na podstawie temperatury. **Nigdy nie dodawać pompy ponownie do pierwszego profilu**.
- Rzeczywisty bilans mocy przyłącza nadal korzysta z pomiaru **Grid** — nie odejmuje EV od realnego importu. Samochód wpływa na dostępny zapas mocy do ładowania magazynu.
- Jeżeli pomiar EV lub pompy nie obejmuje wymaganej godziny, brak wartości jest oznaczany jako brak danych; niespójne pomiary (EV większe niż cały Load) są odrzucane, zamiast udawać dom o zerowym poborze.
- Profile nadal wymagają co najmniej 7 dni kompletnej historii, a cel SOC w obecnej wersji jest liczony przez starszy silnik. Nowy model historyczny nie jest jeszcze wykonywany jako automatyczne sterowanie Deye.

**Po aktualizacji:** pobierz ponownie integrację przez HACS/Marketplace, uruchom ponownie HA i sprawdź `Wersja integracji = 0.3.2`. W sensorze `Uczenie zużycia domu` odczytasz `ev_wliczony_w_dom: true`, `pompa_wliczona_w_dom: true`, a także oba profile. Nie ma potrzeby usuwać integracji ani ponownie wybierać czujników.

## Wersja 0.3.1 — pierwsza nauka zużycia domu (EP20-03)

Nowa encja **Uczenie zużycia domu** pokazuje postęp budowy profilu z 7–30 pełnych dni. W jej atrybutach znajduje się **24-godzinny profil P50 i P90**, oddzielnie dla dni roboczych i weekendów. Przewidywanie jest statystyczne: nie zgaduje, kiedy dokładnie zostanie włączona pralka, tylko pokazuje typowe i wyższe możliwe zużycie danej godziny. Do uczenia kwalifikowane są dni z co najmniej 22 godzinami odczytów i kompletnością minimum 90% w każdej liczonej godzinie. Niepełne dni są pomijane.

**Ważne:** odjęcie EV jest poprawne wyłącznie, jeśli `sensor.deye_load_power` obejmuje także samochód. W **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → Konfiguruj → ustawienia zaawansowane** jest nowe pole **„Samochód: czy moc EV jest wliczona do zużycia Deye Load?”**. Od 0.3.2 **domyślnie wybrane jest `Tak`**, zgodnie z potwierdzonym podłączeniem; starsze `Niepotwierdzone` migruje automatycznie. Po potwierdzeniu `Tak` automatycznie odejmie pomiar ładowarki z pomiaru całego domu. Po `Nie` nie odejmuje, ponieważ auto jest poza licznikiem domu. Brak pomiarów EV nie jest traktowany jako 0 W.

**Na tym etapie** model jest tylko źródłem danych historycznych i wykresów. Planowanie docelowego SOC nadal korzysta ze starszego, ostrożnego modelu. Żeby zastosować nauczone zużycie w sterowaniu, potrzebne są jeszcze symulator przepływów 48h, walidacja sposobu pomiaru i testy dry-run. Automatyzacja Deye pozostaje wyłączona.

## Rozwój 2.0 — zatwierdzony zakres do wdrożenia (2026-11-06)

Projektowany jest nowy silnik planowania magazynu Deye: profil zużycia z 7–30 dni (pralka, kuchenka itd.), pompa zależna od pogody, oddzielne EV, G12w/G13 i ręczne ceny, symulator SOC 48h, raport oszczędności, duży dashboard oraz mały widżet Lovelace. Plan obejmuje **opcjonalne sterowanie TOU Deye**, ze świadomym przełącznikiem **„Włącz automatyzację” (domyślnie wyłączony)**, dry-run, backupem ustawień i odczytem zwrotnym. Aktualna wersja 0.2.7 pozostaje doradcza.

- [Szczegółowa specyfikacja Energy Pilot 2.0](docs/roadmap/ENERGY_PILOT_2_0_SPEC.md)
- [Backlog EP20-01…10 i kryteria odbioru](docs/roadmap/IMPLEMENTATION_BACKLOG_2_0.md)
- [EP20-11: optymalna godzina i moc ładowania magazynu 28 kWh](docs/roadmap/EP20-11_SMART_CHARGING_POWER_28KWH.md)
- [EP20-12: dynamiczny strażnik przyłącza 15 kW, 28 kWh nominalnie, SOC 10–100%, suwak i dziennik decyzji](docs/roadmap/EP20-12_GRID_GUARD_CAPACITY_UI.md)

## Nowość 0.2.7 — czy system działa? Diagnostyka i odświeżanie

Integracja pokazuje odrębnie **czy aktualizuje się**, a także **czy potrafi sporządzić poprawny plan**. Sam fakt odczytania mocy ładowarki nie oznacza jeszcze poprawnej prognozy PV.

**Nowe encje na urządzeniu ESTADI Energy Pilot:**

| Encja (nazwa widoczna) | Znaczenie |
|---|---|
| **Stan systemu** | Działa / Ograniczony / Błąd / Brak odświeżania |
| **Ostatnie odświeżenie** | Czas ostatniej zakończonej aktualizacji |
| **Ostatni poprawny plan** | Czas, kiedy udało się wyliczyć obydwa cele SOC z prawidłową prognozą |
| **Liczba odświeżeń** | Ile razy uruchomiono odświeżenie |
| **Liczba błędów** | Nieoczekiwane wyjątki podczas aktualizacji |
| **Czas ostatniego odświeżenia** | Czas wykonania w milisekundach |
| **Odśwież teraz** | Przycisk wymuszający pobranie danych i ponowne obliczenie |

Aktualizacje odbywają się automatycznie **co 15 minut**. Dodatkowy watchdog co minutę aktualizuje status: jeśli **ponad 35 minut** nie zakończyło się odświeżenie, pokaże **Brak odświeżania**, nawet jeśli ostatni wynik był poprawny.

**Dziennik ostatnich zdarzeń** jest w atrybutach sensora **Stan systemu**. Pokazuje czas, poziom, kod i powód, m.in. brak SOC, problem z temperaturą i błąd prognozy. Wewnętrzny dziennik przechowuje maksymalnie **100 ostatnich zdarzeń** w `.storage`, z czego **20 ostatnich** jest widocznych w atrybutach sensora. Ręczne odświeżenie również zostawia wpis. Kolejne identyczne błędy nie spamują dziennika, ale licznik i czas ostatniego odświeżenia nadal się zmieniają.

**Jak sprawdzić działanie:** po aktualizacji z Marketplace/HACS i restarcie wybierz **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → urządzenie**. Otwórz **Stan systemu** i zobacz `przyczyna` oraz `dziennik_ostatnich_zdarzen`. Kliknij **Odśwież teraz**; po zakończeniu wartość **Ostatnie odświeżenie** powinna się zmienić. Jeśli nadal jest błąd, dziennik poda przyczynę. Nie trzeba usuwać integracji ani ponownie wybierać encji.

Bezpieczeństwo: przycisk **nie ładuje magazynu i nie zmienia ustawień Deye**. Tylko ponownie odczytuje źródła i oblicza zalecenia.

## Wersja 0.2.6 — diagnostyka przy braku SOC lub temperatury

- Sensor **Stan obliczeń** wyświetla teraz, czy brakuje wartości SOC czy temperatury, zamiast wspólnego niejasnego komunikatu.
- W atrybutach sensora znajdziesz pole `diagnostyka`: identyfikatory encji, wartości i przyczyny błędu (brak encji, niedostępność, zła jednostka, wartość poza zakresem).
- Puste wartości zapisane przez stary formularz nie zasłaniają już prawidłowo wykrytych encji Deye i pogody.
- Przy poprawnym czujniku pompy to on służy jako bieżąca temperatura; jeśli nie działa, wykorzystywana jest temperatura z `weather.*`.
- Nadal **nie steruje** falownikiem ani ładowarką.

Po aktualizacji przez Marketplace/HACS i pełnym restarcie HA otwórz sensor **Stan obliczeń** i jego atrybuty. Jeśli problem pozostaje, wklej `diagnostyka` — nie trzeba robić zrzutów całego kreatora.

## Wersja 0.2.5 — temperatura z wbudowanej prognozy pogody

Moduł automatycznie wybiera jedną istniejącą encję `weather.*` (np. pogodę „Dom”) i pobiera z niej aktualną temperaturę z atrybutu `temperature`, jeżeli osobny czujnik temperatury nie jest wybrany albo nie zwraca liczby. Do prognozowania poboru pompy używa także `weather.get_forecasts` z `type: hourly`. Nie trzeba tworzyć osobnego sensora z szablonu. Przy wielu encjach pogodowych wybierz właściwą w zaawansowanych ustawieniach. Jeśli fizyczny czujnik temperatury pompy jest poprawnie wybrany, zachowuje pierwszeństwo dla *aktualnej* temperatury; pogoda nadal służy do prognozy kolejnych godzin. Brak poprawnych danych nie jest interpretowany jako 0°C.

## Home Assistant 2026.11 i nowsze: Marketplace zamiast HACS

Od **Home Assistant 2026.11** HACS nie jest już osobnym dodatkiem: jest częścią systemu jako **Ustawienia → Marketplace**. Po aktualizacji stary HACS jest usuwany, a już **zainstalowane** repozytoria i integracje są automatycznie migrowane.

Jeżeli masz Home Assistant 2026.11 lub nowszy:
1. Otwórz **Ustawienia → Marketplace**.
2. Sprawdź kartę **Zainstalowane / Installed** i wyszukaj `ESTADI Energy Pilot`. Jeśli tam jest, wybierz **Zaktualizuj** i po aktualizacji uruchom ponownie HA.
3. Jeśli go nie ma: wybierz **Dodaj z linku / Add from link** i wpisz `https://github.com/endigarnek/estadi-energy-pilot`.
4. Otwórz stronę repozytorium, wybierz **Instaluj / Install**, sprawdź wersję i ponownie wybierz **Instaluj**. Samo dodanie linku to nie jest instalacja.
5. Po instalacji sprawdź sensor **Wersja integracji** w ustawieniach integracji. Oczekiwane `0.2.4`.

Marketplace wymaga połączenia z GitHub do zarządzania własnymi repozytoriami. Możesz autoryzować publiczny odczyt w **Ustawienia → Marketplace → połącz GitHub**, jeżeli pojawi się taki komunikat.

**Starszy Home Assistant 2026.10 lub wcześniejszy:** stosuj instrukcję HACS poniżej, łącznie z krokiem **Pobierz** po dodaniu repozytorium.

## Jeśli repozytorium znika z HACS lub wczytuje się stary kreator

**Ważne:** samo dodanie adresu do `Custom repositories` / `Własne repozytoria` nie jest instalacją! HACS może **usunąć niepobrane własne repozytorium po restarcie**. Po dodaniu koniecznie trzeba wejść w kartę ESTADI Energy Pilot i kliknąć **Pobierz / Download**, poczekać na potwierdzenie instalacji i dopiero wtedy uruchomić ponownie cały Home Assistant.

1. HACS → trzy kropki → **Własne repozytoria / Custom repositories**.
2. Wklej `https://github.com/endigarnek/estadi-energy-pilot`, typ **Integration / Integracja**, kliknij **Dodaj**.
3. **Bez restartowania**: wróć na listę HACS, wyszukaj `ESTADI Energy Pilot`, otwórz jego kartę, wybierz **Pobierz / Download**. Nie kończ na dodaniu repozytorium.
4. Sprawdź, czy HACS pokazuje **Zainstalowano / Installed** (lub opcję **Pobierz ponownie / Redownload**). Dopiero teraz uruchom ponownie Home Assistant.
5. W Home Assistant → Ustawienia → Urządzenia i usługi → Dodaj integrację → `ESTADI Energy Pilot`. Nowy kreator powinien od razu wykryć już istniejące źródło Forecast.Solar i sensownie nazwać formularz.
6. Po udanym uruchomieniu urządzenie ESTADI Energy Pilot będzie miało sensor **Wersja integracji**, który powinien pokazać `0.2.4`. Jeżeli wciąż widzisz napis `Wersja 0.1` lub stary formularz, Home Assistant uruchamia starszą kopię: pobierz pliki ponownie przez HACS, wykonaj **pełny restart HA** oraz zamknij i otwórz przeglądarkę.

**Nie usuwaj wcześniej działającej integracji** ani plików `.storage`. Nie instaluj równolegle innej kopii modułu. Jeśli dodatek nadal znika po kliknięciu **Pobierz**, sprawdź logi HACS w **Ustawienia → System → Dzienniki** (włącz poziom debug dla `custom_components.hacs`). Może być to błąd HACS / połączenia z GitHub, a nie naszego kodu.

Repozytorium jest *własnym repozytorium HACS*, a nie oficjalną pozycją w katalogu. Nie ma jeszcze pełnej walidacji publikacyjnej (branding/licencja/metadane), co nie jest tym samym co brak możliwości dodania go jako własnego repozytorium. Nie ma również opublikowanych GitHub Releases: HACS pobiera wtedy kod z domyślnej gałęzi `main`.

## Wersja 0.2.3 — Forecast.Solar bez dodatkowych instalacji

**Nie trzeba już instalować Solcast.** Jeżeli w Home Assistant masz wbudowaną integrację **Forecast.Solar**, moduł automatycznie pobiera jej godzinową prognozę przez natywną akcję `forecast_solar.get_forecast` (`resolution: hourly`). Zwracane `wh_period` przeliczamy z Wh na kWh na godzinę. Na podstawie tych danych silnik planuje SOC i zachowuje prognozy w historii.

- Jeśli jest tylko jedna konfiguracja Forecast.Solar, wybierana jest automatycznie.
- Jeżeli jest kilka konfiguracji, najpierw sprawdzamy właściciela sensora `sensor.energy_production_today`. Jeśli to nie daje jednoznacznego wyniku, kreator pokazuje **jedno pole wyboru konfiguracji** — nie sumujemy nieznanych źródeł, aby uniknąć podwójnego liczenia.
- Wcześniej skonfigurowany Solcast pozostaje obsługiwany jako zapasowe źródło prognoz.
- Brak działania `forecast_solar.get_forecast` lub niedostępne dane skutkują komunikatem, a nie fikcyjną prognozą 0 kWh.
- Wersja doradcza — **nie wysyła poleceń do Deye ani ładowarki**.

**Aktualizacja:** HACS → ESTADI Energy Pilot → menu → Pobierz ponownie → pełny restart Home Assistant → odświeżenie przeglądarki. Nowy formularz wyświetla informację, że wybiera Forecast.Solar. Pozostałe wymagane dane to m.in. faktyczna użyteczna pojemność magazynu oraz temperatura na zewnątrz.

**Ważne:** dostępność akcji zależy od wersji Home Assistanta. Wersja nie potwierdza jeszcze działania na Twoim urządzeniu; jeśli po aktualizacji system wyświetla błąd o braku akcji, sprawdź aktualizację Home Assistanta zamiast instalowania Solcast.

## Nowość 0.2.2 — krótki kreator, bez szukania encji

Po aktualizacji przez HACS **pobierz ponownie integrację i uruchom ponownie cały Home Assistant**. W razie widocznego starego opisu („Wersja 0.1”) zamknij kreator i wszystkie karty przeglądarki z Home Assistant, a następnie otwórz panel ponownie. Samo przeładowanie integracji lub aktualizacja metadanych HACS nie wystarczy.

Nowy kreator wyszukuje istniejące sensory, w tym cztery znane encje Deye/PV/dom/Shelly/EV. **Nie wyświetla wykrytych już czujników jako pól wyboru.** Prosi tylko o brakujące źródła Solcast, SOC i temperaturę zewnętrzną, plus dwie wartości: *rzeczywistą użyteczną pojemność magazynu* (bez automatycznego domyślnego 15 kWh) oraz średnią moc bazową domu (domyślnie 400 W; to założenie do weryfikacji).

W istniejącej konfiguracji menu **Konfiguruj** pokazuje prosty ekran (pojemność, moc bazowa, rezerwa i pole „Pokaż zaawansowane ustawienia”). Gdy zaznaczysz pole, przejdziesz do wszystkich encji i harmonogramu. Rozpoznane sensory zapisywane są przy pierwszym zatwierdzeniu kreatora, a w istniejącej konfiguracji są automatycznie wykorzystywane bez reinstalacji.

Jeżeli na formularzu pozostają puste pola Solcast, być może zainstalowana jest tylko integracja **Forecast.Solar**. To inne źródło danych niż **Solcast PV Forecast**; nie należy wybierać Forecast.Solar jako Solcast bez zaimplementowania adaptera.

## Wersja 0.2.1 — automatyczny wybór czujników

Po aktualizacji do **0.2.1** czujniki rozpoznawane są automatycznie, jeśli wciąż istnieją w Home Assistant i raportują właściwe jednostki:

| Pomiar | Automatycznie wybierana encja |
|---|---|
| Deye: produkcja PV (moc) | `sensor.deye_pv_power` |
| Deye: zużycie domu (moc) | `sensor.deye_load_power` |
| Pompa ciepła: moc elektryczna | `sensor.shellyem3_08f9e051e0b0_channel_b_power` |
| Ładowarka EV: rzeczywista moc | `sensor.moc_ladowarki_poprawna` |

W kreatorze oraz na stronie **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → Konfiguruj** moduł podpowiada również jednoznacznie rozpoznane encje **Solcast, SOC Deye i temperatury zewnętrznej**. Jeśli jest więcej pasujących encji albo brak poprawnej jednostki, pole zostaje puste — system niczego nie zgaduje. Wcześniej zapisane ręczne wybory mają pierwszeństwo.

**Nie usuwaj dotychczasowej integracji!** Po aktualizacji moduł zacznie korzystać ze znalezionych czterech czujników również w już istniejącej konfiguracji. Jeżeli chcesz przejrzeć lub zmienić źródła danych, wybierz **Konfiguruj** i zatwierdź. Pojemność użyteczną magazynu trzeba potwierdzić ręcznie — nie da się jej bezpiecznie wywnioskować z samych nazw sensorów. **Wersja nadal nie steruje Deye**.

## Nowość 0.2 — historia prognoz i ładowarki EV

Po aktualizacji wybierz **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → Konfiguruj** i wskaż cztery opcjonalne czujniki:

| Rola | Encja z Twojego Home Assistant |
|---|---|
| Moc paneli | `sensor.deye_pv_power` |
| Moc domu | `sensor.deye_load_power` |
| Moc pompy ciepła | `sensor.shellyem3_08f9e051e0b0_channel_b_power` |
| Moc ładowarki EV | `sensor.moc_ladowarki_poprawna` |

Wartości mocy są przyjmowane **wyłącznie** z czujników o jednostkach W lub kW, a wartości ujemne/nieprawidłowe są pomijane. Historia nie jest uzupełniana zmyślonymi zerami, jeśli HA był wyłączony lub sensor był niedostępny.

**Co zapisujemy** (bez dodatkowej bazy, w wewnętrznym magazynie Home Assistanta `.storage`):

- Około 21:00: **zamrożona prognoza Solcast na następny dzień**, ze szczegółami co godzinę, niepodmieniana w późniejszych aktualizacjach.
- Co 15 minut: zmierzone moce i oszacowana na ich podstawie energia PV, domu, pompy ciepła i ładowarki EV, z pokryciem danych dla każdej godziny.
- Do **45 dni** danych; w czujniku błędu prognozy atrybuty `ostatnie_dni` i `godziny_wczoraj`.
- Różnica prognoza/rzeczywistość liczona wyłącznie dla **zakończonych dni** z co najmniej 90% pokryciem pomiaru PV. W innym przypadku brak oceny, a nie fałszywy wynik.

Czujniki nowej wersji: `Wczorajsza prognoza PV (z 21:00)`, `Wczorajsza produkcja PV — pomiar`, `Błąd wczorajszej prognozy PV`, `Kompletność pomiaru PV wczoraj`, energia ładowarki EV i pompy ciepła (wczoraj), energia EV/PV (dziś).

**To szacunki energii z próbek mocy co 15 minut, a nie odczyty licznika rozliczeniowego.** Porównania prognoz zaczną być sensowne dopiero po zebraniu pełnej doby (z wieczorną prognozą z poprzedniego dnia). Ładowarka 11 kW pracująca przy 10 A ma realnie ok. 6,9 kW; moduł bierze **zmierzone** W, nie wpisaną moc maksymalną. Zużycie domu może już zawierać pompę i EV — **nie sumujemy** ich dodatkowo do domu.

Wersja jest dalej **tylko doradcza**: NIE zapisuje ustawień falownika Deye, NIE reguluje prądu ładowarki i NIE publikuje gotowego panelu Lovelace z wykresami. Zachowane dane godzinowe można wykorzystywać do budowy wykresu porównania w następnym etapie.

## Testy lokalne

```bash
python -m unittest discover -s tests -v
```

GitHub Actions uruchamia również testy przy nowych zmianach.

## Plan

- v0.2: gotowe dane historyczne i sensory. Kolejne: wygodny pulpit Lovelace z wykresem godzinowym.
- v0.3: nauka zużycia domu oraz korekta prognoz na podstawie pomiarów.
- v0.4: najpierw symulacja (dry-run), później opcjonalne sterowanie Deye po sprawdzeniu jego konkretnych encji i ograniczeń.

Zgłoszenia: [Issues](https://github.com/endigarnek/estadi-energy-pilot/issues).
