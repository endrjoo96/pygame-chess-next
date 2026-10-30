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
gracz. W trakcie gry `Esc` zamyka okno, a `Spacja` rozpoczyna partię od nowa.

Na początku każdej partii obaj gracze otrzymują po dwie losowe karty. Ich typ
i liczba użyć są takie same dla obu stron, ale karty są osobnymi instancjami.
Na planszy pojawiają się również karty do zebrania przez figury. Odliczanie do
następnej karty rozpoczyna się w chwili wyłożenia poprzedniej; gdy dojdzie do
zera, nowa karta pojawi się niezależnie od tego, czy inne nadal leżą na planszy.
Licznik tur jest widoczny nad planszą, a zebranie karty nie wpływa na odliczanie.

## Bot

Bot gra czarnymi. Podczas namysłu plansza jest przyciemniona, wyświetla się
animowany spinner oraz najlepszy dotychczas znaleziony ruch. Wyszukiwanie działa
w osobnym wątku, a analizę możliwych ruchów rozdziela między procesy — do liczby
dostępnych logicznych rdzeni. Bot porównuje średnie oceny ruchów dla próbek
ukrytej ręki przeciwnika.

## Konfiguracja

Ustawienia znajdują się w `run.properties`:

| Klucz | Znaczenie |
|---|---|
| `mode` | `PROD` losuje karty planszowe według rzadkości; `DEBUG` wybiera je równomiernie i umieszcza natychmiast. |
| `log.debug.enabled` | Włącza (`true`) lub wyłącza (`false`) logi diagnostyczne. |
| `game.seed` | Opcjonalny seed losowości. Jeśli klucza brakuje, nowy seed 64-bitowy jest losowany przy rozpoczęciu partii. |
| `ai.search.max_depth` | Maksymalna głębokość wyszukiwania AI w półruchach. |
| `ai.search.time_limit_seconds` | Łączny budżet czasu AI na wybranie ruchu, w sekundach. |
| `ai.search.cpu_percent` | Limit workerów AI jako procent logicznych CPU, liczba całkowita od 1 do 100; domyślnie `100`. |

Liczba workerów to `max(1, floor(logiczne_CPU * cpu_percent / 100))`, dodatkowo
ograniczona liczbą zadań wyszukiwania. Na przykład `99` przy 8 logicznych CPU
uruchomi maksymalnie 7 workerów, a `100` — maksymalnie 8. To ogranicza liczbę
procesów obliczeniowych, ale nie gwarantuje dokładnego procentu użycia mierzonego
przez system operacyjny.

Seed może być dowolną liczbą całkowitą, również ujemną lub bardzo dużą.
Ustawienie stałej wartości, np. `game.seed=12345`, pozwala odtwarzać te same
losowania w kolejnych partiach. Usunięcie wpisu powoduje losowanie nowego seeda
przy każdym rozpoczęciu partii. Reset klawiszem `Spacja` zachowuje seed bieżącej
partii.

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
