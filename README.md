# Chess NEXT

Chess NEXT to gra szachowa napisana w Pythonie z użyciem Pygame. Oprócz
standardowych figur gracze korzystają z kart zaklęć zmieniających zasady ruchu,
nakładających efekty lub pozwalających na specjalne akcje.

## Uruchamianie

Wymagany jest Python 3.10 lub nowszy oraz zależności `pygame` i `PyYAML`.
Nie są instalowane automatycznie — zainstaluj je w używanym środowisku:

```shell
python -m pip install pygame PyYAML
```

Uruchom grę z katalogu projektu:

```shell
python -m logic.game_init
```

W menu wybierz **Graj**, aby rozpocząć partię. Przełącznik **Bot czarnych**
pozwala włączyć grę przeciwko AI; gdy jest wyłączony, czarne obsługuje drugi
gracz. W trakcie gry `Esc` otwiera menu pauzy, z którego można wznowić grę,
wrócić do menu głównego, wyjść z aplikacji lub — w trybach `DEBUG` i `DIAG` —
przełączyć okno debugowania AI. Przycisk **Pomoc** w menu głównym i menu pauzy
otwiera instrukcję gry i opisy wszystkich kart.
Bot kontynuuje obliczenia w tle podczas pauzy. `Esc` ponownie wznawia grę, a
`Spacja` rozpoczyna partię od nowa.

Na początku każdej partii obaj gracze otrzymują po dwie losowe karty. Ich typ
i liczba użyć są takie same dla obu stron, ale karty są osobnymi instancjami.
Na planszy pojawiają się również karty do zebrania przez figury. Odliczanie do
następnej karty rozpoczyna się w chwili wyłożenia poprzedniej; gdy dojdzie do
zera, nowa karta pojawi się niezależnie od tego, czy inne nadal leżą na planszy.
Licznik tur jest widoczny nad planszą, a zebranie karty nie wpływa na odliczanie.
Wąski pasek po prawej stronie planszy pokazuje bieżącą ocenę heurystyczną
pozycji (+ dla białych); pasek i liczbowy wynik płynnie przechodzą do nowej oceny.
Ruch figury i użycie karty są animowane; podczas animacji nie można wykonać
następnej akcji.
Menu, pauza i ekran namysłu AI używają rozmytego tła z planszą.

## Wersja webowa i gra sieciowa

Wersja webowa używa Pygbag i nie dołącza modułów AI. GitHub Pages hostuje
statyczną paczkę, a osobny serwer WebSocket obsługuje pokoje i sygnalizację
WebRTC; same akcje gry są przesyłane bezpośrednio między przeglądarkami przez
DataChannel. Host gra białymi, gość czarnymi. Połączenia wymagające serwera
TURN mogą nie zadziałać, ponieważ obecna konfiguracja korzysta wyłącznie z
publicznego serwera STUN.

Aby zbudować paczkę lokalnie, ustaw adres dostępnego serwera sygnalizacyjnego
(`ws://` lokalnie lub `wss://` dla wdrożenia HTTPS) i uruchom:

```shell
python -m pip install -r web/requirements.txt
$env:SIGNALING_SERVER_URL = "wss://twoj-serwer.example"
python web/build.py
```

Wynikiem jest katalog `web/build`, który można opublikować jako statyczną
stronę. `SIGNALING_SERVER_URL` może być pusty, ale wtedy dostępna jest tylko
gra lokalna. Workflow GitHub Actions buduje paczkę i wdraża ją do Pages po
pushu na `master` lub ręcznym uruchomieniu. W ustawieniach repozytorium wybierz
**Settings → Pages → Build and deployment → GitHub Actions** oraz dodaj
zmienną repozytorium Actions `SIGNALING_SERVER_URL` z adresem `wss://`
wdrożonego serwera.

Serwer sygnalizacyjny można uruchomić na dowolnej usłudze obsługującej Python
i WebSocket:

```shell
python -m pip install -r server/requirements.txt
python -m server.signaling
```

Serwer nasłuchuje na `0.0.0.0` i porcie z `PORT` (domyślnie `8765`); w
środowisku lokalnym ustaw `SIGNALING_SERVER_URL` na
`ws://localhost:8765`. Pages nie hostuje procesu serwera.

## Bot

Bot gra czarnymi. Podczas namysłu plansza jest przyciemniona, wyświetla się
animowany spinner. W trybach `DEBUG` i `DIAG` przy partii przeciwko botowi
otwiera się osobne okno statystyk, w którym widać najlepszy dotychczas znaleziony
ruch, jego ocenę i głębokość; po zakończeniu wyszukiwania także wybrany ruch i
liczbę odwiedzonych węzłów. Podczas ponderingu panel pokazuje do pięciu najgroźniejszych ruchów
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
procesy — zgodnie z liczbą workerów ustawioną w `run.yaml`. Bot analizuje
dokładne kopie rąk obu graczy.
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
Klucz obejmuje pełny stan symulacji i zapamiętuje swój hash, co ogranicza koszt
ponownego wczytywania wpisów do cache workerów. Po przesłaniu klucza do innego
procesu hash jest wyliczany ponownie; jego przechowywanie zwiększa zużycie
pamięci proporcjonalnie do liczby kluczy.
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
ruchu. Funkcję można wyłączyć przez `ai.search.ponder.enabled=false`; domyślnie
jest włączona.

## Benchmark ruchów

Powtarzalny benchmark generatora i wyszukiwania AI uruchom z katalogu projektu:

```shell
python -m benchmarks.benchmark_move_generation --seed 20261116 --iterations 3000 --repeats 5 --search-repeats 5
python -m benchmarks.benchmark_move_generation --seed 20261116 --budget-seconds 5 --budget-repeats 3 --workers 1
python -m benchmarks.benchmark_move_generation --seed 20261116 --budget-seconds 5 --workers 2
python -m benchmarks.benchmark_move_generation --seed 20261116 --plies 13 --extended --cache off --budget-seconds 15 --budget-repeats 3
```

Seed wybiera powtarzalną sekwencję początkową; `--plies` określa jej długość
w półruchach i musi być dodatnią liczbą nieparzystą (domyślnie `13`, aby na
ruchu były czarne). Benchmark mierzy generowanie akcji i wyszukiwanie w zwykłej
pozycji oraz z kartami/efektami ruchowymi. `--extended` dodaje pozycję z
kartą planszową, pułapką, ogłuszeniem i dodatkowymi kartami w obu rękach.

Próby o stałej głębokości i z opcjonalnym budżetem czasowym raportują osobno
każdy wynik, ukończoną i rozpoczętą głębokość, liczbę węzłów oraz czasy faz;
podsumowanie zawiera medianę i zakres czasu. W próbach czasowych różne ruchy,
głębokości i liczby węzłów są możliwe między powtórzeniami. `--cache on` lub
`--cache off` pozwala porównać wyszukiwanie z pamięcią i bez niej; domyślne
`auto` wyłącza cache dla stałej głębokości, a włącza go dla prób czasowych.
Każda próba tworzy nową instancję AI i zimną pulę workerów. `--workers` pozwala
porównać koszt analizy równoległej; czas zadań i faz workerów jest sumowany
między procesami, więc może przekraczać czas całego wyszukiwania. Metryki
benchmarku są domyślnie włączone; `--metrics off` pozwala zmierzyć wyszukiwanie
bez dodatkowych timerów i porównać koszt instrumentacji.

Profil funkcji i pamięci wykonuj osobno, bez prób z budżetem czasowym:

```shell
python -m benchmarks.benchmark_move_generation --profile --metrics off --budget-seconds 0 --iterations 300 --repeats 1 --search-repeats 1
python -m benchmarks.benchmark_move_generation --memory-profile --metrics off --budget-seconds 0 --iterations 300 --repeats 1 --search-repeats 1
```

Wyniki `cProfile` i `tracemalloc` zawierają narzut narzędzi diagnostycznych i
nie nadają się do porównywania czasu ruchu. Do porównania wersji użyj tych
samych argumentów; czasy są zależne od sprzętu i nie są testem progowym.

### Pojemność i powtarzalność cache

Osobny benchmark bada limity cache głównego i snapshotów przekazywanych workerom,
powtarzalność pełnych stanów oraz koszt zapisu/odczytu wybranych wpisów:

```shell
python -m benchmarks.benchmark_search_cache --only capacity --budget 5 --repeats 3 --workers 1
python -m benchmarks.benchmark_search_cache --only recurrence --history-plies 24 --game-count 8
python -m benchmarks.benchmark_search_cache --only disk --workers 2
```

Warianty pamięci porównują cache wyłączony, bieżący limit główny `6k`, większe
limity oraz limity snapshotu workerów `64`, `128` i `256` wpisów. Tryb z jednym
workerem (domyślny) mierzy też rzeczywistą pojemność lokalnej tabeli workerów.
Przy wielu procesach konfiguracja zmienia rozmiar przekazywanego snapshotu,
natomiast lokalna tabela każdego procesu pozostaje ograniczona do 256 wpisów.
Na Windowsie benchmark próbuje próbkować sumaryczny prywatny commit oraz
working set (strony rezydentne w RAM-ie) procesu AI i workerów; na innych
systemach raportuje brak tego pomiaru. Przyrost obejmuje cały proces wyszukiwania,
w tym tymczasowe kopie stanów, a nie tylko wpisy cache. Próbki
używają tych samych seedów i naprzemiennej kolejności, a wyniki czasowe,
głębokość, trafienia i wyparcia są raportowane oddzielnie. Każda próba działa
w osobnym procesie, aby poprzednie wyszukiwanie i stan alokatora Pythona nie
zanieczyszczały pomiaru pamięci.

Pomiar powtarzalności odtwarza te same i różne sekwencje ruchów. Pełny klucz
zawiera także ręce, efekty, stan tury i RNG; uproszczone dopasowanie uwzględnia
jedynie stronę na ruchu i rozmieszczenie/typ/przesunięcie figur. Takie dopasowanie
nie jest trafieniem do cache ocen — może służyć najwyżej legalnej wskazówce
kolejności ruchów. Pomiar dyskowy serializuje lokalnie wygenerowane snapshoty
tymczasowymi plikami, pięć razy mierzy zapis z `fsync` i odczyt, raportuje
medianę oraz zakres, a pliki usuwa po każdej próbie. Nie wczytuj pickle
pochodzących z niezaufanych źródeł. Surowe
wyniki są zależne od sprzętu; benchmark nie zmienia `run.yaml` ani nie
włącza trwałego cache do gry.

## Konfiguracja

Ustawienia znajdują się w zagnieżdżonym pliku YAML `run.yaml`. Ścieżki z
kropkami w tabeli opisują odpowiadające im poziomy zagnieżdżenia, np.
`ai.search.cpu.workers` oznacza `ai: search: cpu: workers:`.
Testy pytest używają jego kopii `run.test.yaml`; zmiany w niej nie wpływają na
normalne uruchomienie aplikacji.

| Klucz | Znaczenie |
|---|---|
| `mode` | `PROD` i `DIAG` losują karty planszowe według rzadkości; `DEBUG` wybiera je równomiernie i umieszcza natychmiast. Okno diagnostyczne jest dostępne w `DEBUG` i `DIAG`, ale nie w `PROD`. |
| `ui.action_animation_duration_ms` | Czas animacji ruchu figury i użycia karty w milisekundach; `0` wyłącza animacje, dozwolony zakres to `0`–`2000`. Domyślnie `0`; dostarczony `run.yaml` ustawia `300`. |
| `log.level` | Poziom logów: `ERROR`, `WARN`, `INFO`, `LOGIC`, `DEBUG` lub `OFF`; domyślnie `WARN`. |
| `game.seed` | Opcjonalny seed losowości. Jeśli klucz jest pominięty lub pusty, nowy seed 64-bitowy jest losowany przy rozpoczęciu partii. |
| `ai.search.max_depth` | Maksymalna głębokość wyszukiwania AI w półruchach. |
| `ai.search.time_limit_seconds` | Bazowy budżet czasu AI na wybranie ruchu, w sekundach. W zależności od najwyższej ukończonej głębokości ponderingu dla aktualnego stanu jest liniowo zmniejszany z 100% przy głębokości 1 do 20% przy `ai.search.max_depth`; jeśli nie ma ukończonego wyniku ponderingu, wykorzystywany jest pełny czas. Przy `max_depth=1` budżet pozostaje pełny. Przydzielony czas i parametry obliczenia są logowane na poziomie `INFO`. |
| `ai.search.cpu.workers` | Maksymalna liczba workerów wyszukiwania ruchu; dodatnia liczba całkowita, domyślnie `1`. Liczba aktywnych workerów jest ograniczona liczbą zadań. |
| `ai.search.cpu.worker_usage` | Docelowy udział aktywnego czasu każdego workera, w procentach od `1` do `100`; domyślnie `100`. Ograniczenie jest realizowane przez naprzemienne okresy pracy i bezczynności. |
| `ai.search.ponder.enabled` | Włącza pondering (`true`/`false`); domyślnie `true`. Pondering wymaga `ai.search.cache.enabled=true`. |
| `ai.search.ponder.cpu.workers` | Maksymalna liczba workerów ponderingu; dodatnia liczba całkowita, ograniczona liczbą zadań. Jeśli pominięta, dziedziczy `ai.search.cpu.workers`; gdy pominięte są oba parametry, obowiązuje domyślne `1`. |
| `ai.search.ponder.cpu.worker_usage` | Docelowy udział aktywnego czasu każdego workera ponderingu, w procentach od `1` do `100`. Jeśli pominięty, dziedziczy `ai.search.cpu.worker_usage`; gdy pominięte są oba parametry, obowiązuje domyślne `100`. |
| `ai.search.cache.enabled` | `true` włącza pamięć wyników i wskazówek ruchu; `false` wyłącza ich tworzenie i odczyt. Domyślnie `true`. |
| `ai.search.cache.max_entries` | Maksymalna liczba wpisów pamięci partii; dodatnia liczba całkowita z opcjonalnym sufiksem `k`, `M` lub `G` (mnożniki binarne: 1024, 1024², 1024³). W dostarczonym `run.yaml` ustawiono `6k`. Tabele workerów mają dodatkowy limit. |
| `ai.search.learning.enabled` | Włącza odczyt trwałych wskazówek kolejności ruchów; `false` wyłącza cały mechanizm. Domyślnie `false`, w dostarczonym `run.yaml` ustawiono `true`. |
| `ai.search.learning.save_enabled` | Włącza zapis zebranych wskazówek; przy `false` mechanizm działa tylko do odczytu. Domyślnie `false`, w dostarczonym `run.yaml` ustawiono `true`. Wymaga `ai.search.learning.enabled=true`. |
| `ai.search.learning.database_path` | Ścieżka do bazy SQLite; ścieżki względne są liczone od bieżącego katalogu roboczego. Domyślnie `move-learning.sqlite3`. |
| `ai.search.learning.max_file_size` | Maksymalny rozmiar bazy SQLite z podpowiedziami; co najmniej `16k`, dodatnia liczba z opcjonalnym sufiksem `k`, `M` lub `G` (mnożniki binarne). Domyślnie 1/4 fizycznej pamięci RAM, gdy parametr pominięto; w dostarczonym `run.yaml` ustawiono `16G`. |
| `ai.search.learning.soft_cutoff_threshold` | Próg miękkiego obniżenia priorytetu w perspektywie gracza wykonującego ruch; domyślnie `-20`. Wymaga `ai.search.cache.enabled=true` oraz wiarygodnego wyniku dla tego samego pełnego stanu i głębokości. |
| `ai.search.metrics.enabled` | `true` włącza zbiorcze pomiary faz wyszukiwania, węzłów, odcięć, cache i workerów; raport jest emitowany raz po wyszukiwaniu. `false` wyłącza dodatkowe timery; domyślnie `false`. Benchmark ma osobny przełącznik `--metrics`, domyślnie `on`, i nie zmienia konfiguracji gry. |

Trwała baza zawiera trzy osobne tabele. `move_hints` gromadzi ogólne sygnały
preferowanych, odcinających i słabych zwykłych ruchów; jej wskazówki są
filtrowane względem aktualnych legalnych akcji i służą tylko do kolejności.
Nie zapisuje wskazówek z pozycji z aktywnym efektem, użyciem karty w linii ani
kartą do podniesienia na planszy; niewykorzystane karty na ręce są dozwolone.

`best_moves` przechowuje jeden najlepszy ruch exact na pełną pozycję i wersję
oceny/reguł — wpis zastępuje się tylko wynikiem z co najmniej tak dużej,
ukończonej głębokości. `search_cutoffs` przechowuje osobno wiarygodne granice
alpha-beta (`lower`/`upper`) oraz exact ruchy miękko odcięte, wraz z akcją i
głębokością. Dzięki temu głębszy najlepszy ruch nie usuwa dowodów odcięć dla
alternatyw. Przy migracji starszej tabeli `search_results` jej wpisy są
zachowywane jako dane odcięć; nie są arbitralnie zamieniane na najlepszy ruch.
Klucz wyników to stabilny hash pełnego stanu, obejmującego obie
ręce, efekty, karty planszowe i RNG. Zgodny exact wpis zastępuje obliczenia
tylko na tej samej głębokości; głębszy ruch służy jedynie do porządkowania.
Workery otwierają bazę read-only, a proces główny zapisuje aktualizacje po
ukończonych iteracjach. Pozycja z kartą czekającą na planszy na podniesienie
nie jest źródłem ani odbiorcą wpisów; po podniesieniu karta w ręce tworzy nowy
pełny stan.

Wyniki exact dla zgodnego stanu i głębokości mogą zastąpić ponowne liczenie
akcji, a granice są używane tylko wtedy, gdy rzeczywiście spełniają warunek
bieżącego okna alpha-beta. Wynik poniżej progu `-20` obniża priorytet gałęzi
względem strony na ruchu, ale nie usuwa ruchu z listy legalnych opcji.
Soft-cutoff korzysta wyłącznie z wiarygodnych wyników na tej samej głębokości;
gdy wszystkie ruchy są oznaczone jako słabe, najlepszy z nich jest ponownie
sprawdzany jako awaryjny kandydat. Płytsza analiza nie gwarantuje optymalności
na większej głębokości, a próg pozostaje heurystyką, nie dowodem najlepszego
ruchu w całej partii.

Baza SQLite znajduje się domyślnie w bieżącym katalogu roboczym procesu jako
`move-learning.sqlite3`; jej lokalizację można zmienić przez
`ai.search.learning.database_path` w `run.yaml`. Błąd bazy jest logowany na
poziomie `ERROR`, po czym bot kontynuuje bez trwałych wskazówek. Okno
diagnostyczne pokazuje rozmiar bazy, workery aktualnie pobierające z niej
wskazówki oraz to, czy wybrany ruch miał podpowiedź w bazie.

`cpu.workers` podaje liczbę workerów wprost — nie jest przeliczane względem
liczby logicznych procesorów. `cpu.worker_usage` steruje udziałem czasu pracy
osobno dla każdego workera: przy `50` worker jest aktywny w przybliżeniu przez
połowę czasu. Nie oznacza to 50% łącznej mocy komputera; np. cztery workery po
50% mogą średnio wykorzystać równowartość dwóch logicznych CPU. To uśrednione
ograniczenie przez okresowe bezczynności, a nie twardy limit systemowy, więc
rzeczywisty odczyt systemu może się różnić. Wyszukiwanie i pondering współdzielą
trwałą pulę procesów, a każde z nich ogranicza liczbę zadań do własnego
ustawienia `cpu.workers`.

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
