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

## Priorytety logowania

- `run.properties` używa klucza `log.level`; dopuszczalne wartości to `ERROR`, `WARN`, `INFO`, `LOGIC`, `DEBUG` i `OFF`. Domyślny poziom to `WARN`; logi są wypisywane na stdout z czasem i prefiksem poziomu. Koloruj tylko prefix ANSI, wyłącznie na TTY; respektuj `NO_COLOR` i nie dodawaj kodów ANSI do wyjścia przekierowanego.
- Poziomy są hierarchiczne: wybrany próg pokazuje ten poziom oraz wszystkie bardziej ogólne. `LOGIC` obejmuje `INFO`, `WARN` i `ERROR`, ale nie `DEBUG`. `OFF` wyłącza logi.
- `ERROR` służy błędom wymagającym uwagi; `WARN` — sytuacjom nietypowym z bezpiecznym fallbackiem; `INFO` — istotnym zdarzeniom i wynikom; `LOGIC` — przebiegowi decyzji/zasad gry; `DEBUG` — szczegółom diagnostycznym.
- Loguj proces wyszukiwania AI i symulacji przez `utils.logging` (`log_error`, `log_warn`, `log_info`, `log_logic`, `log_debug`). Nie używaj bezpośrednio `print` ani nie odtwarzaj filtracji w miejscu wywołania. W gorących pętlach unikaj kosztownego formatowania, sprawdzając `is_enabled`; nie loguj każdego węzła wyszukiwania.
- Zmiany kategorii i konfiguracji obejmują testy filtrowania poziomów oraz aktualizację `README.md` i niniejszych instrukcji.

## Wskazówki dotyczące zmian i weryfikacji

- Przy zmianach ruchu, zbić, efektów kart lub tur graczy zachowuj dotychczasowe zasady gry i kolejność tur. Te zachowania są koordynowane w `GameLogicLoop`, procesorach, figurach i funkcjach zachowań zaklęć.
- `GameSimulation.available_actions(state)` udostępnia akcje bieżącego gracza, a `GameSimulation.apply(state, action)` zwraca nowy stan bez modyfikowania wejściowego. Rozszerzaj oba elementy i ich testy, gdy dodajesz akcję gry. Warstwa symulacji używa wspólnych przejść/reguł `GameLogicLoop`, ale nie może zależeć od ekranu ani rysować elementów UI.
- Przy zmianach zasad gry lub działania kart dodawaj albo aktualizuj odpowiednie testy pytest w `tests/`. Zamiast uruchamiać graficzną grę w testach, korzystaj z istniejących lekkich obiektów testowych i atrap.
- Rysowanie w Pygame i dostęp do zasobów pozostaw w istniejących ścieżkach interfejsu i renderowania. Używaj istniejących funkcji pomocniczych do współrzędnych planszy, zamiast powielać konwersję indeksów.
- Stosuj konwencje nazewnictwa, formatowania i importów zgodne z sąsiednim kodem. Część komentarzy i opisów testów jest po polsku — zachowuj ten język podczas ich edycji.
- Nie dodawaj zależności, przepływów pracy ani narzędzi, jeśli zadanie tego nie wymaga. Ponieważ CI nie jest skonfigurowane, po zmianach w kodzie uruchom powyższe pełne polecenie testów pytest. Zgłoś ewentualne ograniczenia środowiska, zamiast twierdzić, że niewykonane sprawdzenie zakończyło się powodzeniem.

## AI bota i przeszukiwanie symulacji

- `models/game_observation.py` jest granicą informacji dla bota: `GameObservation.from_state` przekazuje dokładne kopie obu rąk, a `to_state()` tworzy z nich pełny, odizolowany stan symulacji. Nie przekazuj do wyszukiwania mutowalnego stanu gry ani obiektów interfejsu; zachowuj stan generatora losowego dla przyszłych losowych zdarzeń.
- `logic/game_simulation.py` to interfejs wyszukiwania do reguł gry: `available_actions(state)` generuje legalne akcje, a `apply(state, action)` waliduje je i zwraca nowy stan przez współdzielone `GameRules.apply_action`. Symulacja musi pozostać niezależna od Pygame/UI, nie mutować wejściowego stanu i odzwierciedlać wszystkie reguły, karty oraz efekty gry.
- `logic/chess_ai.py` używa minimaxu z przycinaniem alpha-beta. Wynik jest liczony z perspektywy czarnych; czarne maksymalizują, białe minimalizują. `evaluate` ocenia m.in. materiał, zagrożenia, rozwój, mobilność, karty i dostęp do kart na planszy. Zachowuj tę konwencję znaku w nowych heurystykach i testach.
- Wyszukiwanie iteracyjnie zwiększa głębokość i zachowuje najwyżej oceniony dotąd legalny ruch startowy, nawet jeśli został oceniony w nieukończonej iteracji. Kolejność ruchów (`_order_actions` / `_quick_action_score`) wpływa na skuteczność alpha-beta — wartościowe bicia, promocje, ruchy kartami i zbicie króla są rozpatrywane wcześniej. Zmiany kolejności nie mogą zmieniać legalności ruchów ani deterministycznego rozstrzygania remisów.
- Ruchy początkowe są oceniane równolegle przez `ProcessPoolExecutor`, jeśli dostępnych akcji i limit workerów jest więcej niż jeden. Każdy worker analizuje tę samą migawkę pełnego stanu z dokładnymi rękami obu graczy. Funkcja robocza `_evaluate_root_action` musi pozostać na poziomie modułu, a argumenty i wyniki zadań muszą być serializowalne — procesy Windows używają `spawn`. Nie przekazuj workerom obiektów Pygame ani współdzielonego mutowalnego stanu gry.
- Limit czasu i głębokości z `SearchConfig` oraz `run.properties` jest częścią zachowania bota. W razie przekroczenia budżetu bot ma zachować najlepiej oceniony dotąd legalny ruch startowy, nawet jeśli pochodzi z nieukończonej głębokości; anulowanie i zamykanie puli procesów nie może blokować ani uszkadzać pętli gry. `ai.search.cpu_percent` określa procent logicznych procesorów dla puli, z co najmniej jednym workerem.
- `logic/stage/game_logic_loop.py` uruchamia wybór ruchu asynchronicznie, pobiera wynik dopiero po zakończeniu i odbiera aktualizacje bieżącego kandydata przez callback. Utrzymuj UI responsywne, a callbacki postępu bezpieczne przy współbieżności; nie manipuluj interfejsem z procesów wyszukiwania.
- Przy zmianach AI aktualizuj `tests/test_chess_ai.py` i, jeśli dotyczą symulacji lub obserwacji, odpowiednie testy `test_game_simulation.py` / `test_game_observation.py`. Pokrywaj legalność wyniku, przekazanie obu dokładnych rąk, perspektywę oceny, limity budżetu oraz zgodność wyników wyszukiwania szeregowego i równoległego.
- Nie zastępuj alpha-beta A* bez uzasadnienia: gra jest naprzemienną grą adversarialną, a nie problemem znajdowania najtańszej ścieżki do znanego celu. Ulepszanie kolejności ruchów jest naturalnym sposobem priorytetyzacji w obecnym algorytmie. MCTS/PUCT może być osobną alternatywą dla rozdzielania symulacji, ale musi uwzględniać przeciwnika i wysoką rozgałęzioność akcji; porównuj je na tych samych stanach, budżecie czasu i metrykach, nie usuwając dotychczasowego wyszukiwania bez testów.
