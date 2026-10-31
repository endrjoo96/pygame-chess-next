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

## AI bota i przeszukiwanie symulacji

- `models/game_observation.py` jest granicą informacji dla bota: `GameObservation.from_state` przekazuje własną rękę i liczbę kart przeciwnika, ale nie ujawnia ich typów. `determinize(rng)` tworzy pełny, niezależny stan przez losowanie ukrytej ręki zgodnie z rozkładem kart. Nie omijaj tej granicy, przekazując botowi rzeczywisty stan przeciwnika.
- `logic/game_simulation.py` to interfejs wyszukiwania do reguł gry: `available_actions(state)` generuje legalne akcje, a `apply(state, action)` waliduje je i zwraca nowy stan przez współdzielone `GameRules.apply_action`. Symulacja musi pozostać niezależna od Pygame/UI, nie mutować wejściowego stanu i odzwierciedlać wszystkie reguły, karty oraz efekty gry.
- `logic/chess_ai.py` używa minimaxu z przycinaniem alpha-beta. Wynik jest liczony z perspektywy czarnych; czarne maksymalizują, białe minimalizują. `evaluate` ocenia m.in. materiał, zagrożenia, rozwój, mobilność, karty i dostęp do kart na planszy. Zachowuj tę konwencję znaku w nowych heurystykach i testach.
- Wyszukiwanie iteracyjnie zwiększa głębokość i zachowuje wynik ostatniej ukończonej głębokości. Kolejność ruchów (`_order_actions` / `_quick_action_score`) wpływa na skuteczność alpha-beta — wartościowe bicia, promocje, ruchy kartami i zbicie króla są rozpatrywane wcześniej. Zmiany kolejności nie mogą zmieniać legalności ruchów ani deterministycznego rozstrzygania remisów.
- Ruchy początkowe i próbki ukrytych rąk są oceniane równolegle przez `ProcessPoolExecutor`, jeśli dostępnych zadań i limit workerów jest więcej niż jeden. Funkcja robocza `_evaluate_root_action` musi pozostać na poziomie modułu, a argumenty i wyniki zadań muszą być serializowalne — procesy Windows używają `spawn`. Każdy worker analizuje izolowany stan; nie przekazuj mu obiektów Pygame ani współdzielonego mutowalnego stanu gry.
- Limit czasu i głębokości z `SearchConfig` oraz `run.properties` jest częścią zachowania bota. W razie przekroczenia budżetu bot ma zachować najlepszą legalną akcję bazową lub wynik ostatniej ukończonej głębokości; anulowanie i zamykanie puli procesów nie może blokować ani uszkadzać pętli gry. `ai.search.cpu_percent` określa procent logicznych procesorów dla puli, z co najmniej jednym workerem.
- `logic/stage/game_logic_loop.py` uruchamia wybór ruchu asynchronicznie, pobiera wynik dopiero po zakończeniu i odbiera aktualizacje bieżącego kandydata przez callback. Utrzymuj UI responsywne, a callbacki postępu bezpieczne przy współbieżności; nie manipuluj interfejsem z procesów wyszukiwania.
- Przy zmianach AI aktualizuj `tests/test_chess_ai.py` i, jeśli dotyczą symulacji lub informacji ukrytej, odpowiednie testy `test_game_simulation.py` / `test_game_observation.py`. Pokrywaj legalność wyniku, reprodukowalność deterministycznych próbek, perspektywę oceny, limity budżetu oraz zgodność wyników wyszukiwania szeregowego i równoległego.
- Nie zastępuj alpha-beta A* bez uzasadnienia: gra jest naprzemienną grą adversarialną, a nie problemem znajdowania najtańszej ścieżki do znanego celu. Ulepszanie kolejności ruchów jest naturalnym sposobem priorytetyzacji w obecnym algorytmie. MCTS/PUCT może być osobną alternatywą dla rozdzielania symulacji, ale musi uwzględniać przeciwnika, niepełną informację o kartach i wysoką rozgałęzioność akcji; porównuj je na tych samych stanach, budżecie czasu i metrykach, nie usuwając dotychczasowego wyszukiwania bez testów.
