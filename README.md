# Chess NEXT

Chess NEXT to gra szachowa napisana w Pythonie z użyciem Pygame. Oprócz
standardowych figur gracze korzystają z kart zaklęć zmieniających zasady ruchu,
nakładających efekty lub pozwalających na specjalne akcje.

## Uruchamianie

Uruchom grę z katalogu projektu:

```shell
python -m logic.game_init
```

W menu wybierz **Graj**, aby rozpocząć partię. Przełącznik **Bot czarnych**
pozwala włączyć grę przeciwko AI; gdy jest wyłączony, czarne obsługuje drugi
gracz. W trakcie gry `Esc` otwiera menu pauzy, z którego można wznowić grę,
wrócić do menu głównego, wyjść z aplikacji lub przełączyć okno debugowania AI.
Bot kontynuuje obliczenia w tle podczas pauzy. `Esc` ponownie wznawia grę, a
`Spacja` rozpoczyna partię od nowa.

Na początku każdej partii obaj gracze otrzymują po dwie losowe karty. Ich typ
i liczba użyć są takie same dla obu stron, ale karty są osobnymi instancjami.
Na planszy pojawiają się również karty do zebrania przez figury. Odliczanie do
następnej karty rozpoczyna się w chwili wyłożenia poprzedniej; gdy dojdzie do
zera, nowa karta pojawi się niezależnie od tego, czy inne nadal leżą na planszy.
Licznik tur jest widoczny nad planszą, a zebranie karty nie wpływa na odliczanie.

## Bot

Bot gra czarnymi. Podczas namysłu plansza jest przyciemniona, wyświetla się
animowany spinner. Przy partii przeciwko botowi otwiera się osobne okno
statystyk, w którym widać najlepszy dotychczas znaleziony ruch, jego ocenę i
głębokość; po zakończeniu wyszukiwania także wybrany ruch i liczbę odwiedzonych
węzłów. Podczas ponderingu panel pokazuje do pięciu najgroźniejszych ruchów
białych, uszeregowanych wyłącznie według oceny z perspektywy czarnych; głębokość
nie wpływa na ranking. Wynik ruchu pochodzi z oceny pozycji po ruchu białych i
najlepszej znalezionej odpowiedzi czarnych (głębokość 2, czyli dwa półruchy).
Panel na bieżąco pokazuje także fazę pracy (`wyszukiwanie` lub `pondering`),
liczbę odwiedzonych węzłów oraz aktualnie badaną i ostatnią ukończoną głębokość.
Zajętość głównego cache i sumę wpisów w
lokalnych cache workerów pokazuje osobno — cache workerów mogą zawierać kopie
tych samych wpisów.
Licznik węzłów workerów jest odświeżany porcjami, aby ograniczyć narzut.
Widoczne są też wyparcia i bieżący stan każdego workera (`not-started`, `starting`,
`initializing`, `busy` lub `idle`);
lista mieści 24 workery, a przy większej liczbie można ją przewijać kółkiem myszy.
Wyszukiwanie szeregowe pokazuje worker lokalny. Okno jest pozbawione górnej belki
i można je przesuwać, przeciągając dowolne miejsce. Zamknięcie okna statystyk nie
przerywa partii.
Wyszukiwanie działa w osobnym wątku, a analizę możliwych ruchów rozdziela między
procesy — do liczby dostępnych logicznych rdzeni. Bot analizuje dokładne kopie rąk obu graczy.
Przy głębszym wyszukiwaniu stosuje redukcję późnych spokojnych ruchów (LMR);
obiecujące warianty są ponownie sprawdzane z pełną głębokością, a bicia
i akcje kart pozostają bez redukcji.
Przy `log.level=DEBUG` logowane jest również podsumowanie wyszukiwania: liczba
workerów, czas, ukończona głębokość, odwiedzone węzły, tempo węzłów na sekundę
oraz wybrany ruch i jego ocena.
Domyślnie bot przechowuje ograniczoną pamięć wyników między iteracjami i turami
tej samej partii. Zapamiętane ruchy mogą zmieniać kolejność przeszukiwania;
oceny i granice alpha-beta są używane tylko dla tej samej głębokości i gdy ich
wiarygodność nie została naruszona przez redukcje LMR. Pamięć jest czyszczona
przy rozpoczęciu nowej partii i nie gwarantuje szybszego ani lepszego ruchu.
Przy `DEBUG` podawane są także liczby trafień, użytych ocen, wskazówek ruchu,
wpisów i usunięć z pamięci.
Na początku partii bot korzysta również z niewielkiego zestawu klasycznych
otwarć do czwartego półruchu. Legalne ruchy książkowe jedynie zmieniają
kolejność przy równym wyniku heurystycznym — nie zastępują oceny AI ani nie
pomijają ruchów kartami.
Po ruchu czarnych bot może w trakcie tury białych analizować ich możliwe
odpowiedzi i dalsze warianty. Pondering nie ma limitu czasu; kończy się po
osiągnięciu maksymalnej głębokości, zapełnieniu pamięci albo wykonaniu ruchu
przez białe. Wyniki są zachowywane w pamięci i mogą przyspieszyć następny wybór
ruchu. Po każdym wyborze zachowywana jest tylko gałąź wybranego przez bota
ruchu. Funkcja jest domyślnie wyłączona.

## Konfiguracja

Ustawienia znajdują się w `run.properties`:

| Klucz | Znaczenie |
|---|---|
| `mode` | `PROD` losuje karty planszowe według rzadkości; `DEBUG` wybiera je równomiernie i umieszcza natychmiast. |
| `log.level` | Poziom logów: `ERROR`, `WARN`, `INFO`, `LOGIC`, `DEBUG` lub `OFF`; domyślnie `WARN`. |
| `game.seed` | Opcjonalny seed losowości. Jeśli klucz jest pominięty lub pusty, nowy seed 64-bitowy jest losowany przy rozpoczęciu partii. |
| `ai.search.max_depth` | Maksymalna głębokość wyszukiwania AI w półruchach. |
| `ai.search.time_limit_seconds` | Bazowy budżet czasu AI na wybranie ruchu, w sekundach. W zależności od najwyższej ukończonej głębokości ponderingu dla aktualnego stanu jest liniowo zmniejszany z 100% przy głębokości 1 do 20% przy `ai.search.max_depth`; jeśli nie ma ukończonego wyniku ponderingu, wykorzystywany jest pełny czas. Przy `max_depth=1` budżet pozostaje pełny. Przydzielony czas i parametry obliczenia są logowane na poziomie `INFO`. |
| `ai.search.cpu_percent` | Limit workerów AI jako procent logicznych CPU, liczba całkowita od 1 do 100; domyślnie `100`. |
| `ai.search.ponder.cpu_percent` | Procent puli workerów przeznaczony na pondering podczas tury białych, liczba całkowita od 0 do 100; brak klucza oznacza `0` i wyłącza pondering. Wymaga `ai.search.cache.enabled=true`. Dla wartości dodatniej liczba workerów wynosi `ceil(rozmiar_puli * procent / 100)`. |
| `ai.search.cache.enabled` | `true` włącza pamięć wyników i wskazówek ruchu; `false` wyłącza ich tworzenie i odczyt. Domyślnie `true`. |
| `ai.search.cache.max_entries` | Maksymalna liczba wpisów pamięci partii; dodatnia liczba całkowita z opcjonalnym sufiksem `k`, `M` lub `G` (mnożniki binarne: 1024, 1024², 1024³). W dostarczonym `run.properties` ustawiono `64k`. Tabele workerów mają dodatkowy limit. |

Liczba workerów to `max(1, floor(logiczne_CPU * cpu_percent / 100))`, dodatkowo
ograniczona liczbą zadań wyszukiwania. Na przykład `99` przy 8 logicznych CPU
uruchomi maksymalnie 7 workerów, a `100` — maksymalnie 8. To ogranicza liczbę
procesów obliczeniowych, ale nie gwarantuje dokładnego procentu użycia mierzonego
przez system operacyjny.

### Poziomy logów

Logi trafiają na standardowe wyjście z lokalnym znacznikiem czasu i nazwą poziomu.
Prefix jest kolorowany tylko w terminalu: `ERROR` na czerwono, `WARN` na żółto,
`INFO` na cyjanowo, `LOGIC` na zielono, a `DEBUG` na szaro. Kolor obejmuje
wyłącznie prefix; jest wyłączany przy przekierowaniu wyjścia oraz po ustawieniu
zmiennej środowiskowej `NO_COLOR`.
Ustawienie `log.level` wskazuje najniższy poziom, który ma być wyświetlany:
każdy poziom zawiera również komunikaty poziomów bardziej ogólnych. `LOGIC`
pokazuje więc też `INFO`, `WARN` i `ERROR`, natomiast nie pokazuje `DEBUG`.
`OFF` całkowicie wyłącza logowanie.

| Poziom | Przeznaczenie | Przykładowe komunikaty |
|---|---|---|
| `ERROR` | Operacja nie powiodła się i wymaga uwagi. | Błąd wyszukiwania AI lub odrzucona nielegalna akcja symulacji. |
| `WARN` | Wystąpiła nietypowa sytuacja, ale aplikacja kontynuuje działanie. | Timeout wyszukiwania i użycie najlepszego znanego ruchu. |
| `INFO` | Najważniejsze zdarzenia cyklu życia i końcowe wyniki. | Rozpoczęcie partii lub myślenia AI, wybrany ruch i zwycięzca. |
| `LOGIC` | Przebieg decyzji bota i reguł gry. | Ruchy, bicie, użycie kart i ukończone poziomy wyszukiwania. |
| `DEBUG` | Szczegółowe dane diagnostyczne. | Wyniki poszczególnych kandydatów, statystyki symulacji i losowanie kart. |
| `OFF` | Wyłącza wszystkie logi. | — |

Seed może być dowolną liczbą całkowitą, również ujemną lub bardzo dużą.
Ustawienie stałej wartości, np. `game.seed=12345`, pozwala odtwarzać te same
losowania w kolejnych partiach. Pominięcie wpisu albo ustawienie `game.seed=`
powoduje losowanie nowego seeda przy każdym rozpoczęciu partii. Reset klawiszem
`Spacja` zachowuje seed bieżącej partii.

## Notacja ruchów bota

Notacja wyświetlana przez AI jest uproszczonym zapisem specyficznym dla tej gry,
a nie pełną notacją SAN. Pola zapisane są małymi literami od `a1` do `h8`.
Ruch figury składa się z jej symbolu i pola docelowego; `x` oznacza bicie.

| Figura / akcja | Zapis | Przykład |
|---|---|---|
| Król | `K` | `Ke2` |
| Hetman | `H` | `Hd4` |
| Wieża | `W` | `Wa1` |
| Goniec | `G` | `Gf4` |
| Skoczek | `S` | `Sf3` |
| Pion | bez symbolu | `e4` |
| Bicie | `x` przed polem docelowym | `Gxe5`, `exd5` |
| Akcja pasywna na figurze | `@` i pole figury | `S@f3` |
| Teleportacja | pole źródłowe `↔` pole docelowe | `We2↔e5` |
| Awans | pole figury `=` i symbol nowej figury | `e7=H` |
| Wskrzeszenie | symbol wskrzeszanej figury `@` pole docelowe | `G@f4` |

Przy biciu pionem przed `x` podawana jest kolumna pola źródłowego, np. `exd5`.
Zapis nie dodaje oznaczeń szacha, mata ani rozstrzygania niejednoznacznych
ruchów. Ruchy specjalne korzystające z kart opisują akcję w uproszczonej formie.

## Zrzuty ekranu

### Menu
![Menu gry](https://user-images.githubusercontent.com/24194821/57589722-cf907c00-74eb-11e9-9318-822abd6c9942.png)

### Rozgrywka
![Rozgrywka](https://user-images.githubusercontent.com/24194821/57589721-cf907c00-74eb-11e9-8def-bf4782315ed9.png)

### Zwycięzca
![Ekran zwycięzcy](https://user-images.githubusercontent.com/24194821/57589723-cf907c00-74eb-11e9-8b42-aef703c3e1f8.png)
