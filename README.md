# ESTADI Energy Pilot — wersja 0.3.3 (beta)

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
