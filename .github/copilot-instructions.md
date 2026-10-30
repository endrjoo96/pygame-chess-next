# Instrukcje dla Copilota

## Opis projektu

To szachowa gra napisana w Pythonie 3 z użyciem Pygame, zawierająca niestandardowe karty zaklęć. Pętla gry, renderowanie, zasady ruchu, efekty kart i zasoby planszy są częścią aplikacji; projekt nie ma osobnego backendu ani etapu generowania kodu.

- `logic/stage/`: menu główne i pętla obsługi tur.
- `logic/game_simulation.py`: generowanie akcji oraz symulowanie ich na kopii stanu bez inicjalizowania interfejsu Pygame.
- `processors/`: obsługa ruchu, wejścia, kart i zbitych figur.
- `models/`: figury, zaklęcia i karty, pozycje początkowe oraz niezależny od UI `GameState`.
- `enchants_behaviors/`: funkcje ruchu i inne zachowania wykorzystywane przez zaklęcia.
- `constants/` i `utils/`: typy wyliczeniowe, funkcje pomocnicze do współrzędnych planszy, współdzielony kontekst gry, logowanie i konfiguracja uruchomienia.
- `res/`: obrazy wczytywane przez grę podczas działania.
- `tests/`: testy `pytest` sprawdzające zasady gry i działanie kart.

Przy zmianach zachowania korzystaj z istniejącej struktury i funkcji pomocniczych. Logikę zasad umieszczaj w odpowiedniej warstwie modeli, procesorów lub zachowań, zamiast dodawać ją do renderowania albo obsługi wejścia. Pola planszy mają identyfikatory `1`–`64`; funkcje pomocnicze w `constants/pos.py` zamieniają je na pary współrzędnych `[x, y]` indeksowane od zera.

## Środowisko i polecenia

Repozytorium nie zawiera pliku deklarującego zależności uruchomieniowe, pliku blokady wersji, konfiguracji budowania ani przepływu CI. Zależność deweloperska `pytest` jest deklarowana w `requirements-dev.txt`. Aplikacja importuje `pygame` i używa składni wymagającej Pythona 3.10 lub nowszego. Jeśli w środowisku brakuje Pygame, zainstaluj je w tym środowisku (`python -m pip install pygame`), nie dodając niezamówionego pliku zależności uruchomieniowych.

Polecenia uruchamiaj z katalogu głównego repozytorium. Ścieżki do zasobów, takie jak `res/board.png`, są względne wobec bieżącego katalogu roboczego.

```text
python -m pip install -r requirements-dev.txt
python -m pytest -v
python piecesprite.py
```

Pierwsze polecenie instaluje zależności deweloperskie, drugie uruchamia zestaw testów z czytelnym wynikiem każdego testu, a trzecie uruchamia aplikację Pygame. Nie zakładaj, że skonfigurowano linter ani polecenie budowania.

Plik `run.properties` musi zawierać wartość `DEBUG` albo `PROD` dla `mode`. W trybie `DEBUG` karty są losowane z jednakowym prawdopodobieństwem, a w trybie `PROD` stosowane są skonfigurowane wagi rzadkości. Nie zmieniaj tego lokalnego ustawienia uruchomieniowego w ramach niezwiązanych prac.

## Wskazówki dotyczące zmian i weryfikacji

- Przy zmianach ruchu, zbić, efektów kart lub tur graczy zachowuj dotychczasowe zasady gry i kolejność tur. Te zachowania są koordynowane w `GameLogicLoop`, procesorach, figurach i funkcjach zachowań zaklęć.
- `GameSimulation.available_actions(state)` udostępnia akcje bieżącego gracza, a `GameSimulation.apply(state, action)` zwraca nowy stan bez modyfikowania wejściowego. Rozszerzaj oba elementy i ich testy, gdy dodajesz akcję gry. Warstwa symulacji używa wspólnych przejść/reguł `GameLogicLoop`, ale nie może zależeć od ekranu ani rysować elementów UI.
- Przy zmianach zasad gry lub działania kart dodawaj albo aktualizuj odpowiednie testy pytest w `tests/`. Zamiast uruchamiać graficzną grę w testach, korzystaj z istniejących lekkich obiektów testowych i atrap.
- Rysowanie w Pygame i dostęp do zasobów pozostaw w istniejących ścieżkach interfejsu i renderowania. Używaj istniejących funkcji pomocniczych do współrzędnych planszy, zamiast powielać konwersję indeksów.
- Stosuj konwencje nazewnictwa, formatowania i importów zgodne z sąsiednim kodem. Część komentarzy i opisów testów jest po polsku — zachowuj ten język podczas ich edycji.
- Nie dodawaj zależności, przepływów pracy ani narzędzi, jeśli zadanie tego nie wymaga. Ponieważ CI nie jest skonfigurowane, po zmianach w kodzie uruchom powyższe pełne polecenie testów pytest. Zgłoś ewentualne ograniczenia środowiska, zamiast twierdzić, że niewykonane sprawdzenie zakończyło się powodzeniem.
