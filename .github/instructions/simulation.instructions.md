---
applyTo: "logic/game_simulation.py,logic/game_rules.py,models/game_state.py,models/game_observation.py,tests/test_game_simulation.py,tests/test_game_observation.py"
---

# Instrukcje dotyczące kroku symulacji

## Granica i wejście symulacji

- Węzłem symulacji jest pełny `GameState`, a nie sama pozycja figur. Stan obejmuje m.in. obie ręce, figury zbite, efekty i ogłuszenia figur, karty na planszy, pułapki, prawa bicia w przelocie, liczniki tur, etap ruchu podwójnego oraz stan RNG. Wyszukiwanie musi zachować te dane, bo wpływają na legalne akcje lub przyszłe przejścia.
- `GameState.clone()` tworzy odizolowaną kopię mutowalnych obiektów. Każda gałąź wyszukiwania musi operować na własnym potomku, nie zmieniając stanu rodzica ani innych wariantów.
- Przy przekazywaniu stanu z aktywnej gry do bota używaj migawki `GameObservation` i `to_state()`. Migawka zawiera dokładne, niezależne kopie obu rąk — nie ukrywaj kart przeciwnika i nie przekazuj do symulacji obiektów UI ani mutowalnego stanu aktywnej partii.

## Generowanie akcji

- Generowanie potomków zaczyna się od `GameSimulation.available_actions(state)`. Jeśli król został już zbity, zwracana lista jest pusta.
- W przeciwnym razie generator bierze pod uwagę wyłącznie figury bieżącego gracza, ich ograniczenia ruchu i stan specjalny tury. Zwykłe ruchy korzystają ze wspólnego `process_possible_basic_moves`, a bicie w przelocie i roszada z reguł `GameRules`. Generator dodaje też dostępne akcje kart, np. ruch kartowy, nałożenie efektu, promocję, teleport, wskrzeszenie, pułapkę, trebusz lub rekrutację piona, uwzględniając typ figury, rękę, zajęte pola i aktywne efekty.
- Każdy element listy jest kompletną domenową `GameAction`, nie kliknięciem ani częściową instrukcją UI. Zawiera typ akcji i odpowiednie pozycje, indeks karty, a w razie potrzeby indeks zbitej figury lub pozycję pomocniczą.
- Pola planszy zapisuj jako identyfikatory `1`–`64`; konwersję na współrzędne wykonuj istniejącymi funkcjami z `constants/pos.py`.
- Etapy wieloczęściowej tury są reprezentowane przez pola `GameState`. Po pierwszym kroku `PIECE_DOUBLE_MOVE` tura może pozostać u tego samego gracza, a generator ogranicza następne akcje do kontynuacji tej figury. Nie łącz takich etapów w skrót, który pomija przejścia stanu.

## Zastosowanie akcji i utworzenie potomka

- Typowy krok wyszukiwania ma kolejność: pobierz akcje dla bieżącego stanu → wybierz jedną akcję → utwórz stan potomny → oceń go lub dalej rozwijaj. Nie modyfikuj rodzica przy przygotowaniu potomka.
- Publiczne `GameSimulation.apply(state, action)` ponownie sprawdza, czy akcja należy do aktualnego zbioru legalnych akcji. Nielegalną akcję loguje jako błąd i odrzuca przez `ValueError`. Po walidacji kopiuje stan i stosuje akcję do kopii; używaj tej ścieżki dla akcji pochodzących z zewnątrz lub bez gwarancji, że nadal pasują do stanu.
- Wewnętrzne `GameSimulation._apply_generated_action(state, action)` pomija ponowne generowanie i walidację. Wolno go użyć wyłącznie dla akcji właśnie wygenerowanej z dokładnie tego, niezmienionego stanu. Nadal tworzy kopię i przekazuje ją do `GameRules.apply_action`.
- `GameRules.apply_action` mutuje przekazany stan. Nie wywołuj go bezpośrednio na stanie rodzica w wyszukiwaniu — zmieniłoby to bieżącą gałąź i mogło zanieczyścić pozostałe warianty.
- `GameRules.apply_action` wykonuje skutki domenowe akcji: przesuwa albo usuwa figury, zapisuje zbicia, zużywa lub odrzuca kartę, zbiera kartę planszową oraz aktualizuje efekty, pułapki, prawa specjalne i liczniki. Zależnie od rodzaju akcji może przełączyć gracza, uruchomić gotowe opóźnione efekty i wygasić pułapki.
- `APPLY_BUFF` nie kończy tury, natomiast `APPLY_PASSIVE` ją kończy. Nie zakładaj, że każda akcja zużywająca kartę zmienia gracza.

## Losowość, zakończenie i spójność reguł

- `GameSimulation.apply` domyślnie ustawia `advance_board_card_clock=False`: przejście nie losuje ani nie wykłada przyszłej karty planszowej tylko dlatego, że symulacja doszła do końca tury. Bieżące skutki akcji, w tym zebranie już leżącej karty, nadal są stosowane.
- Jeśli konkretne zadanie wymaga prognozowania zegara kart planszowych, przekaż jawnie `advance_board_card_clock=True`. Przejście użyje wtedy RNG odtworzonego ze stanu rodzica i zapisze nowy stan RNG wyłącznie w potomku. Zachowuj `random_state` w kopiach i kluczach stanu, aby warianty nie dzieliły ani nie gubiły losowości.
- Dla każdej nowej akcji utrzymuj spójność generatora i przejścia: jeśli akcja ma być dostępna, `available_actions` musi przekazać wszystkie dane wymagane przez `GameRules.apply_action`. Zmiany skutków wprowadzaj we wspólnych regułach, nie jako osobną kopię logiki w AI lub UI.
- Po utworzeniu potomka można go ocenić albo wywołać dla niego `available_actions` i kontynuować rekurencję. Kolejność rozpatrywania potomków może wpływać na wydajność przycinania, ale nie może zmieniać ich legalności ani skutków.
- Gra kończy się wyłącznie po eliminacji króla przeciwnika. Nie dodawaj szacha, mata, pata ani zakazu ruchu narażającego króla.

## Testowanie kroku

- Używaj lekkich obiektów `GameState`; nie uruchamiaj Pygame w testach symulacji.
- Dla nowej lub zmienionej akcji sprawdź jej generowanie, zastosowanie, oczekiwane skutki w stanie potomnym oraz niezmienność rodzica, w tym figur, kart i RNG.
- Dodaj przypadki brzegowe właściwe dla danej mechaniki, zwłaszcza dotyczące końca tury, kontynuacji wieloetapowej akcji, zbicia króla i efektów kart.
