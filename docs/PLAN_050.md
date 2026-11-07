# ESTADI Energy Pilot 0.5.0 — plan 48h i bezpieczne uruchomienie Deye

## Co widać na pulpicie

W zakładce **Pulpit** w sekcji „Plan magazynu” zobaczysz prognozowany start, średnią moc ustawioną w doradczym planie, energię dokupioną do magazynu, docelowy SOC i miniwykres godzin ładowania. Dane pojawiają się tylko przy dostępnym wstępnym planie i pełnym scenariuszu dla miniwykresu.

Zakładka **Prognoza 48h** zawiera kartę **Godzinowy harmonogram magazynu — 48h**:

- **Pomarańczowe słupki:** symulowane ładowanie magazynu z sieci (średnia moc w godzinie, nie ustawienie Deye).
- **Zielone słupki:** prognozowane ładowanie magazynu z nadwyżki PV.
- **Niebieskie słupki:** prognozowane rozładowanie magazynu na potrzeby domu.
- **Zielona linia SOC:** przebieg przy uwzględnieniu proponowanego ładowania z sieci.
- **Przerywana linia SOC:** przebieg bez dodatkowego ładowania z sieci.

Przyciski z datami przełączają pierwsze i drugie 24 godziny. Pod wykresem jest tabela godzinowa: godzina, tryb, ładowanie sieciowe i PV, rozładowanie, import z sieci oraz SOC obu wariantów.

## Wiarygodność

To **dwie symulacje na identycznych pomiarach, prognozie PV, profilu domu, pompie ciepła i założeniu EV**. Model rozlicza energię co 15 minut, a interfejs agreguje ją do godzin. Nie zgadujemy przyszłych sesji EV; system nie ukrywa niekompletnej prognozy. W przypadku brakujących godzin nie pokazuje pełnych sum 48h.

Koszty nie są rzeczywistą oszczędnością. Porównywanie scenariuszy z różnym końcowym SOC wymaga uwzględnienia wartości energii pozostałej w magazynie.

## Zakładka „Testy”

- „Sprawdź odczyty sieci i baterii” — surowa moc, jednostki, aktualność, source entity
- „Sprawdź kalibrację kierunków” — znak importu Deye i ładowania magazynu
- „Sprawdź Grid Guard i fazy” — przyłącze 15 kW, bufor, limity każdej fazy
- „Sprawdź prognozę i plan” — długość i pierwsza luka prognozy PV
- „Sprawdź harmonogram Deye TOU” — sześć programów, 24 pola
- „Sprawdź dostępność regulacji mocy” — kandydaci `number`, `select`, `switch` wraz z nazwą, jednostką, zakresem i krokiem. **To wykrywanie encji, nie test zapisu.**
- „Sprawdź gotowość sterowania” — jednoznaczna lista blokad: Grid Guard, fazy, BMS, brak testu odczytu zwrotnego i procedury rollback.

### Co potrzebujemy z rzeczywistego Home Assistant przed TESTEM ZAPISU

Po instalacji 0.5.0 naciśnij „Sprawdź dostępność regulacji mocy (bez zapisu)”, otwórz encję **Laboratorium — wynik testu** i prześlij jej atrybut `szczegoly.candidates`. Potrzebna jest też informacja, czy sterowanie realizuje integracja Deye Cloud, Modbus LAN czy inny model. Następnie przygotujemy dla wskazanych encji i firmware osobny test: odczytaj → zrób migawkę → sprawdź limity → zapisz niewielką zmianę → potwierdź reakcję → przywróć ustawienia; z automatycznym wyłączeniem przy awarii.

**Nie należy w ciemno próbować zmiany mocy podczas jednoczesnego ładowania EV, pompy ciepła i baterii.** Hardware musi sam zabezpieczać instalację i ograniczenia przyłącza; Home Assistant nie jest zamiennikiem zabezpieczeń.

## Instalacja

Instalacja HACS/Marketplace śledząca `main` może wykryć wersję `0.5.0`. Po aktualizacji uruchom ponownie Home Assistant; zarządzany dashboard `*-managed.yaml` powinien zostać odświeżony. Jeśli zasób karty JS jest zbuforowany, wykonaj pełne odświeżenie przeglądarki (`Ctrl+F5`). Nie twórz kolejnych numerowanych pulpitów.

## Status sterowania

**Stan fizycznego zapisu Deye: WYŁĄCZONY.** Kontrolki testowe są tylko do odczytu. Żaden przycisk z tej wersji nie wysyła polecenia do falownika, a 48h harmonogram to nadal propozycja.
