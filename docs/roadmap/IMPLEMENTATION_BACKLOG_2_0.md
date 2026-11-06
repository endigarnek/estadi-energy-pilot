# Backlog wdrożeniowy ESTADI Energy Pilot 2.0
Data: 2026-11-06. Specyfikacja nadrzędna: [ENERGY_PILOT_2_0_SPEC.md](./ENERGY_PILOT_2_0_SPEC.md).

## Priorytet P0 — trzeba mieć, zanim algorytm otrzyma prawo sterowania

| ID | Temat | Weryfikowalne kryteria odbioru |
|---|---|---|
| EP20-01 | Harmonogram i ceny G12w, G13, własna | Kalendarz weekendów/świąt i DST; profile sezonowe, 3 strefy; ręczne ceny import/export; jednostkowe testy co najmniej 15 dat granicznych i przejścia DST; zero fikcyjnych cen |
| EP20-02 | Dane Deye i topologia EV | Integracja istniejących encji i liczników kWh, kontrola jakości, wykrycie EV wewnątrz Deye Load vs poza; żadne podwójne liczenie, uzgodnienie rachunku mocy/energii |
| EP20-03 | Profil domu 7/14/30 dni + pompa | Historia 15 min, wykluczenie EV, P50/P90, weekday/weekend, temperatura, CWU jako niepewność; walidacja na odłożonych dniach z wcześniejszym modelem 400W |
| EP20-04 | Symulacja 48h + decyzje | SOC w przedziałach 15 min, ograniczenia magazynu/BMS, najniższy SOC i marginesy; różnice rano vs w południe; podgląd „dlaczego”, scenariusze słońce/chmury/pobór szczytowy |
| EP20-05 | Skuteczność i raport kosztów | PV forecast snapshot 21:00 vs liczniki Deye; niepełne dane oznaczone; scenariusze bez magazynu / obecny / optymalny; koszty netto + energia/cykle/straty, oszczędność nie udaje wykonanego wyniku |

## Priorytet P1 — UX/dashboard

| ID | Temat | Kryteria odbioru |
|---|---|---|
| EP20-06 | Duży panel i mały widżet | Czytelny mobilny dashboard: SOC prognozowany vs aktualny, PV, dom, pompa, EV, ceny, decyzje, status i oszczędności. Miniwidget 3 linie i kliknięcie do planu, scenariusz brak danych |
| EP20-07 | Intuicyjne ustawienia | Domyślne konkretne encje z obecnej instalacji, formularz cen, taryf, parametrów magazynu, typowy tryb bez YAML; test UI bez instalowania dodatkowych kart |

## Priorytet P2 — sterowanie sprzętem (po P0)

| ID | Temat | Kryteria odbioru |
|---|---|---|
| EP20-08 | Read-only adapter Deye TOU i zabezpieczenia | Identyfikacja modelu i encji writable, odczyt wszystkich 6 slotów, snapshot / backup / limity, alarmy, sprawdzenie parametrów i stanu odpowiedzi, brak zapisów na etapie read-only |
| EP20-09 | Dry-run i replayer | 7 pełnych dni bezpiecznej symulacji: planowane komendy + spodziewany SOC + dziennik błędów; test awarii HA, Deye, temperatury, PV i zmian taryfy |
| EP20-10 | Przełącznik „Włącz automatyzację” OFF + prawdziwy zapis TOU | Tylko za osobnym potwierdzeniem; jawna historia zapisów przed/po; readback, histereza, rate limit, rollback; blokady na błędy / brak zasilania i wyłączenie automatyki po awarii |

## Zasady wdrażania
- Wszystko na osobnych gałęziach `feature/ep20-XX-...`, Pull Request; `main` zmieniać tylko po testach.
- Kod algorytmu ma być testowalny bez Home Assistant, integracja HA to cienka warstwa odczytu/sterowania.
- Nie pytać ponownie o podane encje, nie zgadywać baterii, taryfy i cen.
- Żadnych automatycznych zapisów do Deye bez EP20-01…05 i EP20-08…09.
- Automatyzacja jest **funkcją opcjonalną** i OFF od instalacji, choć użytkownik będzie mógł ją ręcznie włączyć po weryfikacji.
- Testy w GitHub Actions: Python + hassfest + scenariusze + osobne testy bezpieczeństwa Deye.

## Dane do potwierdzenia przed EP20-10
1. Faktura i rzeczywista taryfa G12w z dystrybucją/cenami lub wskazanie G13 po zmianie.
2. Model Deye z tabliczki i dostępność zapisu TOU w działającej integracji.
3. Pojemność magazynu, dolna rezerwa, limit mocy przyłącza i potwierdzenie wliczania EV w Deye Load.

## Przepływ gotowości
`Zebrane minimum 7 dni → model zużycia → symulator i backtest → panel → adapter Deye tylko odczyt → 7 dni dry-run → użytkownik świadomie uruchamia automatyzację`.

Oznaczać wersje rozwojowe w planie jako `0.3.x` (P0), `0.4.x` (P1), `0.5.x` (P2), bez deklarowania sztywnych terminów.
