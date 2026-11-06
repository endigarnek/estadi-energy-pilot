# Miniwidżet ESTADI Energy Pilot 0.3 — bez dodatkowej karty HACS

Wersja beta tworzy encję **Szybki status energii** i nowe czujniki: przyłącze, zapas mocy, strefa taryfy, początek taniego okna, status planu, moc i cel SOC.

W Home Assistant:
1. **Przegląd → Edytuj pulpit → Dodaj kartę → Encje**.
2. Dodaj encję **ESTADI Energy Pilot Szybki status energii** oraz **Grid Guard — status**, **Plan ładowania — moc zalecana**, **Plan ładowania — start**, **Stan systemu**, **Wersja integracji**.
3. Zapisz. Karta pokazuje, czy system działa, dlaczego ogranicza pobór i co *sugeruje*, a nie co wykonał na Deye.
4. Z menu szczegółów sensora **Szybki status energii** otwórz atrybuty: aktualna moc PV/dom/pompa/EV, status przyłącza i proponowany harmonogram.

Jeżeli wartości są niedostępne:
- `brak kalibracji` oznacza, że nie potwierdzono kierunku mocy importu/baterii.
- `brak SOC` oznacza nieprawidłowy sensor poziomu baterii.
- `brak taryfy` oznacza brak odpowiedniego okna według profilu.
- Nie zastępuj `unknown` zerem. W razie wątpliwości użyj **Odśwież teraz** i sprawdź dziennik urządzenia.

**Dopiero następny etap** będzie obejmował pełny wykres 48h SOC/kW/PLN z instalacją jednego dashboardu. Do tej pory ani miniwidżet, ani przycisk „Odśwież teraz” nie wysyłają komend ładowania.
