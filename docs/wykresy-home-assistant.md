# Wykres prognoza vs rzeczywistość — bez dodatkowych kart

Od wersji 0.2 integracja publikuje dwa czujniki z wartościami za **ostatnią ukończoną godzinę**:

- **PV: prognoza poprzedniej godziny** — energia przewidziana poprzedniego wieczora o 21:00.
- **PV: rzeczywista poprzednia godzina** — energia oszacowana na podstawie odczytów mocy falownika.

Każda z wartości jest podana w **kWh na godzinę**, a nie kW. Zmieniają się co godzinę.
Wartość rzeczywista jest niedostępna, jeśli odczyty nie pokryły przynajmniej 90% godziny.

## Panel Energia — własna karta

1. Wejdź w **Przegląd → Edytuj pulpit → Dodaj kartę**.
2. Wybierz wbudowaną kartę **Wykres historii (History graph)**.
3. Dodaj obie encje z ESTADI Energy Pilot.
4. Ustaw czas wyświetlania na **48 godzin** i zapisz.

Jeżeli korzystasz z edytora YAML, zamień przykładowe identyfikatory poniżej na dokładne identyfikatory encji widoczne w Twoim Home Assistant:

```yaml
type: history-graph
title: Prognoza vs rzeczywista produkcja PV
hours_to_show: 48
entities:
  - entity: sensor.TWOJA_ENCJA_PROGNOZY_PV_POPRZEDNIA_GODZINA
    name: Prognoza PV (kWh/h)
  - entity: sensor.TWOJA_ENCJA_RZECZYWISTA_PV_POPRZEDNIA_GODZINA
    name: Produkcja PV (kWh/h)
```

To standardowa historia HA (zależna od ustawień Recorder, domyślnie zwykle 10 dni).
**Niezależnie** od Recorder moduł przechowuje do 45 dni danych w pliku pamięci integracji.
Szczegółowe wartości 24 godzin i ostatnie dni znajdziesz w atrybutach czujnika
**Błąd wczorajszej prognozy PV**, w polach `godziny_wczoraj` i `ostatnie_dni`.

## Ograniczenia i wiarygodność

- Prognoza jest zapamiętywana około 21:00 **poprzedniego dnia**. Jeśli HA był wtedy wyłączony albo Solcast nie dostarczył pełnej prognozy, brak oceny na następny dzień.
- Rzeczywistą energię szacujemy z mocy pobieranej co 15 minut. Zmienność pogody między odczytami może powodować niedokładności.
- Dni niekompletne nie dostają procentowego błędu. Nie interpolujemy długich przerw.
- Zapis nie steruje magazynem Deye ani mocą ładowania EV.
