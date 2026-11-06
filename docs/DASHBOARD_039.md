# ESTADI Energy Pilot 0.3.9 — pełny pulpit i miniwidżet Home Assistant

Od wersji **0.3.9** integracja potrafi przygotować **dwa gotowe pliki YAML** pulpitu Home Assistant. Wykorzystuje **wyłącznie standardowe karty** — bez HACS ApexCharts, Mushroom, Plotly czy zewnętrznych skryptów. Niczego nie zmienia w Deye.

## 1. Generowanie plików — jeden przycisk

1. Zaktualizuj ESTADI Energy Pilot do **0.3.9** i uruchom ponownie Home Assistant.
2. Wejdź w **Ustawienia → Urządzenia i usługi → ESTADI Energy Pilot → urządzenie**.
3. Znajdź przycisk **„Wygeneruj pulpit i miniwidżet YAML”** i naciśnij go **raz**.
4. Otwórz szczegóły przycisku, a w atrybutach znajdziesz `pulpit_yaml` i `miniwidzet_yaml`, z dokładną lokalizacją wygenerowanych plików:
   - `/config/estadi-energy-pilot-dashboard.yaml`
   - `/config/estadi-energy-pilot-mini.yaml`
5. Otwórz plik przez **File Editor**, Studio Code Server lub udział plików Home Assistant. Skopiuj jego **całą treść**.
6. Przejdź do Home Assistant → **Ustawienia → Pulpity**, utwórz **nowy pusty pulpit** o nazwie `ESTADI Energia`. Otwórz go, wybierz **Edytuj pulpit → menu trzech kropek → Edytor konfiguracji surowej / Raw configuration editor**, zamień zawartość nowego pulpitu na skopiowany YAML i zapisz.
7. Analogicznie możesz utworzyć drugi, mały pulpit z pliku `estadi-energy-pilot-mini.yaml`, albo przenieść jego karty do własnego dashboardu.

**Ważne:** plik YAML nie pojawi się sam jako nowy pulpit. Wersja 0.3.9 celowo **nie modyfikuje istniejących dashboardów** i nie korzysta z niestabilnych wewnętrznych API Lovelace. Jedynie przycisk uruchamia eksport, a użytkownik wybiera, na którym pulpicie go zaimportować.

## 2. Co jest na pełnym pulpicie

- **Podsumowanie** — bieżący SOC, PV, moc na Deye Load obejmującą cały dom, samochód EV, pompa, import z sieci.
- **Plan ładowania** — cel SOC, czas rozpoczęcia i końca, proponowana moc, aktualna taryfa/cena, powody ograniczeń.
- **Grid Guard** — aktualny pobór i dostępny zapas 15 kW przyłącza, stan pomiarów L1/L2/L3, brak ręcznego sterowania.
- **Historia 24h** — trzy natywne wykresy: źródła mocy (PV, dom, EV, pompa), SOC magazynu i moc importu/zapas przyłącza. Wykresy historyczne wymagają, żeby HA Recorder miał już zebrane dane.
- **Prognoza na 48h** — energia i SOC po każdym modelowanym przedziale; zbudowana jako *tabela co 4 godziny* z atrybutu `harmonogram_48h` (pełne 48 punktów godzinowych jest dostępne w atrybucie sensora). Natywny `history-graph` nie potrafi pokazać danych z przyszłości, dlatego nie udajemy, że to wykres przyszłego SOC; wykres takiej prognozy będzie osobnym etapem niestandardowej karty.
- **Dziennik dry-run** — ostatnie decyzje hipotetyczne, ograniczenia mocy, przypadki zakończenia EV, bez faktycznych poleceń Deye.
- **Weryfikacja trafności** — porównanie zamrożonych prognoz SOC (+3/+6/+12/+24h) z pomiarem oraz WAPE prognozy PV.
- **Diagnostyka TOU Deye** — stan odczytu sześciu programów i blokad automatyzacji.
- **Ręczne odświeżenie** — wyłącznie przycisk przeliczenia modelu.

## 3. Co jest na miniwidżecie

Kompaktowy status z bieżącym SOC, PV, importem i EV, ostatnią hipotetyczną decyzją oraz najbliższym celem ładowania magazynu. Przydatne na telefonie lub istniejącym głównym pulpicie Home Assistanta.

## 4. Jak dobierane są ID sensorów?

Generator **nie zgaduje nazw encji**. Odczytuje `Entity Registry` Home Assistanta i przypisuje właściwe `entity_id` według stabilnych `unique_id` utworzonych przez ESTADI Energy Pilot. Dzięki temu działa, nawet kiedy zmienisz nazwy sensorów w HA. Dodatkowo korzysta z wcześniej wybranych źródeł pomiaru (SOC, PV, Deye Load, EV, pompa). Brakujące opcjonalne źródła po prostu pomija w wykresach.

Jeśli główne encje modelu zostały wyłączone w rejestrze urządzeń, generator zgłasza **błąd ze wskazaniem brakującej encji**, zamiast tworzyć panel z fikcyjnymi ID.

## 5. Bezpieczeństwo i ponowny eksport

- Przycisk **nigdy nie nadpisuje** wcześniejszego eksportu. Jeżeli pliki już istnieją, tworzy `-2.yaml`, `-3.yaml` itd. Nie modyfikuje nawet pliku, który później samodzielnie edytujesz.
- Do YAML trafiają wyłącznie identyfikatory sensorów i szablony kart. Nie zapisuje tokenów HA, loginów ani danych uwierzytelniających.
- Użyte karty Lovelace mogą nie wyglądać identycznie na różnych motywach; są natywne i korzystają z jasnego/ciemnego wyglądu Home Assistanta.
- Pulpit **nie steruje Deye ani EV**. Nie ma kart zapisujących nastawy. Nawet gdy Grid Guard obliczy 10 kW wolnej mocy, jest to zalecenie, a nie gwarancja ochrony 15 kW lub ograniczenia poszczególnych faz.
- Prognoza magazynu 48h nadal modeluje **brak dodatkowego ładowania z sieci i nieznane przyszłe sesje samochodu**. Nie pokazujemy wymyślonych oszczędności netto w PLN.

## 6. Gdy czegoś nie widać

- **Przycisk eksportu nie istnieje** → sprawdź sensor `Wersja integracji` (wymagane 0.3.9), uruchom ponownie HA.
- **Błąd brakującej encji** → wejdź w urządzenie ESTADI i odblokuj brakujący sensor; ponów eksport.
- **Wykres pusty** → HA Recorder potrzebuje historii; nie traktuj pustego wykresu jako 0 W.
- **Prognoza pusta** → sprawdź `Symulacja 48h — stan` oraz Forecast.Solar. Przy niepełnej prognozie nie tworzymy pozornych wartości.
- **Plik nie jest widoczny w File Editor** → otwórz katalog konfiguracji HA (`/config`), nazwę sprawdź w atrybutach przycisku. Nie jest to plik w folderze `custom_components`.

Wersja 0.3.9 nie zmienia mechanizmu ładowania ani konfiguracji falownika, tylko sposób prezentacji i eksportu istniejących pomiarów oraz prognoz.
