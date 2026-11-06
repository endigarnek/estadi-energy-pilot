# ESTADI Energy Pilot 0.4.6 — pulpit zarządzany

## Co zostało zmienione

- Pięć zakładek: Pulpit (nowy ekran główny), Historia, Prognoza 48h, Koszty, Diagnostyka.
- Pulpit główny pokazuje rzeczywiste encje PV, magazynu, Deye Load, EV i pompy. Deye Load zawiera EV i pompę; wartości nie są sumowane podwójnie. Wskaźnik przyłącza używa **limitu skonfigurowanego**, zamiast liczby na stałe.
- Dane w kartach są aktualizowane z Home Assistant na żywo. Nie ma potrzeby klikania „Wygeneruj” przy zmianie odczytów. Wersja 0.4.6 automatycznie synchronizuje tylko wcześniej wygenerowane i niezmodyfikowane pliki po restarcie HA.
- Generator zapisuje **zawsze te same trzy pliki**: `/config/estadi-energy-pilot-dashboard-managed.yaml`, `/config/estadi-energy-pilot-mini-managed.yaml`, `/config/www/estadi-energy-pilot-ui-v046.js`.
- Stare `dashboard.yaml`, `dashboard-2.yaml`, `dashboard-3.yaml` i podobne nie są automatycznie kasowane ani modyfikowane.
- Jeśli zmienisz ręcznie plik `*-managed.yaml`, eksporter wstrzyma aktualizację (ochrona danych). Po uruchomieniu HA błąd synchronizacji zostanie zalogowany, lecz integracja pomiarowa nie zatrzyma się.
- Miniwidżet jest teraz **jedną responsywną kartą w trybie `compact`**; można skopiować jej konfigurację z `views[0].cards[0]` pliku mini.

## Jednorazowe podłączenie pulpitu w Home Assistant

**Opcja zalecana — dashboard YAML zarządzany przez integrację**

1. Zaktualizuj integrację przez HACS, uruchom ponownie Home Assistant i użyj przycisku „Wygeneruj pulpit, miniwidżet i wykres 48h”.
2. W Home Assistant przejdź do Ustawienia → Pulpity → Zasoby i dodaj URL `/local/estadi-energy-pilot-ui-v046.js` jako **Moduł JavaScript**. Sprawdź, czy nie jest już zarejestrowany. Nie rejestruj dwa razy tego samego zasobu.
3. W File Editor dodaj poniższy blok do `/config/configuration.yaml`. Jeśli istnieje już sekcja `lovelace:`, **dopisz wyłącznie `dashboards:` wewnątrz istniejącej sekcji**, nie duplikuj `lovelace:` ani nie nadpisuj aktualnej konfiguracji.

```yaml
lovelace:
  dashboards:
    estadi-energy-pilot:
      mode: yaml
      filename: estadi-energy-pilot-dashboard-managed.yaml
      title: ESTADI Energy Pilot
      icon: mdi:solar-power
      show_in_sidebar: true
```

4. W Narzędzia deweloperskie → YAML sprawdź konfigurację i uruchom ponownie Home Assistant, aby dashboard pojawił się w menu.
5. Od teraz nowy widok korzysta ze stałego pliku. Po aktualizacji integracji i restarcie HA pliki zarządzane synchronizują się automatycznie. Przy zmianie układu wybierz na pulpicie menu → **Odśwież**, aby odczytać nowy YAML. Same **dane encji** aktualizują się automatycznie bez tego kroku.

### Alternatywa — obecny pulpit edytowany przez UI

Jeśli wolisz zachować obecny pulpit `Energia`, możesz otworzyć nowy plik `*-managed.yaml`, skopiować jego zawartość do edytora YAML istniejącego pulpitu i zapisać. **W tym wariancie kolejne aktualizacje układu NIE będą przenosiły się automatycznie**, ponieważ UI przechowuje kopię konfiguracji. Rekomendowana jest konfiguracja osobnego pulpitu YAML powyżej.

## Ważne ograniczenia i bezpieczeństwo

- Stan `unknown` i `unavailable` pozostaje nieznany. Nie zastępuj go zerem.
- Wykresy historii korzystają z danych dostępnych w rejestratorze HA. Prognoza 48h pozostaje wyłącznie doradcza.
- Na tym etapie integracja **nie przełącza Deye, nie ustawia mocy ładowania i nie kontroluje fizycznie przyłącza**. Wyświetlany limit jest pobierany z konfiguracji Grid Guard (obecnie 15 kW) i stanowi kontekst doradczy.
- Przycisk eksportu nie modyfikuje automatycznie `configuration.yaml`, Twoich istniejących pulpitów ani zasobów UI.
- Stare pliki możesz usunąć dopiero po sprawdzeniu, czy żaden istniejący pulpit nie odwołuje się do nich przez `filename:`. Zalecamy wtedy zachowanie jednej ręcznej kopii poza HA.
