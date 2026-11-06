# Aktualizacje ESTADI Energy Pilot bez ręcznego ZIP

## Zasada działania

Repozytorium `endigarnek/estadi-energy-pilot` jest źródłem modułu. Zmiany zaakceptowane w gałęzi `main` są widoczne jako nowe wersje w HACS lub w Home Assistant Marketplace (od Home Assistant 2026.11). Repozytorium nie ma obecnie opublikowanych GitHub Releases, dlatego menedżer aktualizacji śledzi najnowszy commit gałęzi domyślnej.

**Ważne:** GitHub nie ma dostępu do Twojego Home Assistant i nie może sam zainstalować aktualizacji. Integracja pobrana ręcznie jako ZIP też nie będzie aktualizowana przez HACS, dopóki jej repozytorium nie zostanie zainstalowane i śledzone przez HACS/Marketplace.

## Jednorazowo: śledzenie modułu w HACS lub Marketplace

1. W HACS (Home Assistant starszy niż 2026.11) dodaj własne repozytorium `https://github.com/endigarnek/estadi-energy-pilot` jako **Integration**, jeśli jeszcze nie jest dodane. W Home Assistant 2026.11+ użyj **Ustawienia → Marketplace → Dodaj z linku**.
2. Zainstaluj ESTADI Energy Pilot za pomocą menedżera, nie z paczki ZIP. Jeśli dotąd była instalacja ręczna, przed zmianą wykonaj kopię zapasową i sprawdź zainstalowane encje. Nie zakładaj drugiej instancji integracji — menedżer ma przejąć tę samą ścieżkę `custom_components/estadi_energy_pilot`.
3. W **Ustawienia → Aktualizacje** lub na ekranie repozytorium znajdź encję aktualizacji należącą do ESTADI Energy Pilot (domena `update.`). Zapisz jej rzeczywisty identyfikator; nazwa może być różna w różnych instalacjach.
4. Pierwszą aktualizację wykonaj ręcznie, sprawdź działanie integracji i w razie potrzeby uruchom ponownie Home Assistant.

## Opcjonalnie: całkowicie automatyczna instalacja kolejnych aktualizacji

Przygotowany blueprint: [ESTADI — automatyczne aktualizacje](../blueprints/estadi_energy_pilot_auto_update.yaml).

1. W Home Assistant przejdź do **Ustawienia → Automatyzacje i sceny → Schematy → Importuj schemat**.
2. Wklej URL: `https://github.com/endigarnek/estadi-energy-pilot/blob/main/blueprints/estadi_energy_pilot_auto_update.yaml`.
3. Utwórz automatyzację z zaimportowanego schematu i wskaż **wyłącznie encję aktualizacji ESTADI Energy Pilot**.
4. Wybierz godzinę (domyślnie 03:45). Automatyzacja uruchamia `update.install` tylko wtedy, gdy stan tej encji wynosi `on`, czyli aktualizacja jest dostępna.
5. Ustaw, czy Home Assistant ma automatycznie uruchamiać się ponownie po instalacji. **Domyślnie opcja jest wyłączona**, aby nie przerywać pozostałych automatyzacji. Bez restartu nowy kod integracji Python może nie zostać załadowany aż do ręcznego restartu.
6. Zrób kopię zapasową Home Assistant i pozostaw regularne backupy włączone.

Schemat czeka na potwierdzenie zainstalowania aktualizacji (stan encji `off`, do 20 minut). W razie braku potwierdzenia kończy wykonanie bez restartu.

**Ograniczenie:** automatyczna aktualizacja rozszerzenia nie oznacza automatycznej rejestracji nowego pulpitu w Home Assistant. Pierwsza konfiguracja YAML i zasobu JavaScript jest opisana w [DASHBOARD_046.md](DASHBOARD_046.md). W kolejnych wersjach generator aktualizuje już istniejące pliki zarządzane.

## Bezpieczeństwo

- Automatyzacja dotyka jedynie encji aktualizacji wybranej ręcznie przez Ciebie; nie aktualizuje Home Assistant Core, pozostałych integracji ani urządzeń.
- Restart jest osobną, opcjonalną decyzją. Restart może na chwilę przerwać automatyzacje, a stan bezpieczeństwa instalacji elektrycznej musi wynikać z urządzeń i ich fizycznych zabezpieczeń, nie z Home Assistant.
- Nie dodawaj niesprawdzonych gałęzi deweloperskich ani prerelease jako źródła automatycznych aktualizacji.
- Jeśli HACS/Marketplace nie raportuje aktualizacji lub encja jest niedostępna, automatyzacja nie uruchomi instalacji.

Źródła: [Home Assistant 2026.11 Marketplace](https://www.home-assistant.io/blog/2026/11/04/release-202611), [Automatyczna instalacja aktualizacji](https://www.home-assistant.io/integrations/update/), [Import schematów](https://www.home-assistant.io/docs/automation/using_blueprints).
