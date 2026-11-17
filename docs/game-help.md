# Instrukcja gry Chess NEXT

## Cel gry

- Białe wykonują pierwszy ruch, potem gracze wykonują akcje na zmianę.
- Wygrywa gracz, który zbije lub usunie króla przeciwnika.
- Gra nie używa szacha, mata ani pata: król może wejść na atakowane pole, a ruch nie jest odrzucany z powodu zagrożenia króla.
- Ruchy figur mogą być zmieniane przez zaklęcia. Dostępne pola są podświetlane po wybraniu figury.

## Sterowanie

- Kliknij własną figurę, a następnie podświetlone pole, aby wykonać ruch.
- Kliknij kartę w swojej ręce, a potem wybierz figurę lub pole wskazane przez jej opis.
- Niektóre karty wymagają kilku kliknięć, na przykład wskazania wieży, piona i pola docelowego dla trebusza.
- Ruch na pole z kartą planszową zbiera ją do ręki, o ile gracz nie ma już maksymalnej liczby kart.
- `Esc` otwiera lub zamyka menu pauzy. `Spacja` rozpoczyna partię od nowa.
- Podczas animacji ruchu lub karty wejście gracza jest chwilowo wstrzymane.

## Oznaczenia kart

- **PASSIVE — efekt pasywny:** karta zostaje przypisana do figury i uruchamia swój efekt zgodnie z opisem. Zastosowanie karty kończy turę.
- **BUFF — wzmocnienie:** zmienia sposób poruszania się figury. Zastosowanie nie kończy tury, więc przed ruchem można nałożyć kilka wzmocnień.
- **REUSABLE — wielokrotnego użytku:** liczba przy ikonie oznacza pozostałe użycia. Karta zostaje w ręce, dopóki nie zużyje ostatniego.
- **DELAY_BEFORE_USE — opóźnienie:** liczba przy ikonie oznacza liczbę tur przed uruchomieniem efektu.
- **STUN_AFTER_USE — ogłuszenie:** liczba przy ikonie oznacza długość ogłuszenia figury po użyciu karty. Ogłuszona figura nie może się poruszać ani otrzymywać zaklęć.
- **MANDATORY — efekt obowiązkowy:** nie ma osobnej ikonki. Taki efekt ma pierwszeństwo i zatrzymuje łączenie kolejnych modyfikatorów ruchu tej figury.
- Karta może mieć kilka oznaczeń naraz; liczby pod ikonami dotyczą tej ikony.

## Karty zaklęć

### Skok do przodu

- **Wymagana figura:** pion. **Oznaczenia:** wielokrotnego użytku, 1–3 użycia.
- Pion może wykonać ruch o dwa pola do przodu.

### Ruch do tyłu

- **Wymagana figura:** pion. **Oznaczenie:** BUFF.
- Pion może cofać się o jedno pole i zbijać po skosie do tyłu.

### Pułapka runiczna

- **Wymagana figura:** skoczek.
- Postaw runę na pustym sąsiednim polu. Pierwsza figura, która na nią wejdzie lub przez nią przejdzie, ginie. Runa znika po dwóch kolejnych turach rzucającego.

### Oficer

- **Wymagana figura:** pion. **Oznaczenie:** PASSIVE.
- Sąsiednie sojusznicze piony naśladują ruch oficera, korzystając z jego aktywnych efektów pasywnych.

### Trebusz

- **Wymagana figura:** wieża. **Oznaczenia:** wielokrotnego użytku, 1–2 użycia; ogłuszenie po użyciu: 1 tura.
- Wystrzel piona sąsiadującego z wieżą na puste pole w promieniu pięciu pól. Wieża zostaje ogłuszona na jedną turę.

### Rekrut

- **Wymagana figura:** dowolna. **Oznaczenie:** wielokrotnego użytku, 1–5 użyć.
- Stwórz piona na pustym polu linii startowej: linii 1 dla białych lub linii 8 dla czarnych.

### Przesunięcie skoczka

- **Wymagana figura:** skoczek. **Oznaczenie:** wielokrotnego użytku, 1–3 użycia.
- Skoczek może poruszyć się o jedno pole w dowolnym kierunku.

### Wystrzał wieży

- **Wymagana figura:** wieża.
- Wieża może przeskakiwać nad sojuszniczymi figurami, ale nie może ich zbijać.

### Wystrzał hetmana

- **Wymagana figura:** hetman. **Oznaczenie:** efekt obowiązkowy.
- Hetman może przeskakiwać nad sojusznikami do czterech pól, ale nie może zbijać.

### Kamikaze

- **Wymagana figura:** pion. **Oznaczenie:** PASSIVE.
- Pion detonuje i niszczy wszystkie figury w promieniu jednego pola, także sojusznicze.

### Kamikaze z opóźnieniem — 1 tura

- **Wymagana figura:** pion. **Oznaczenia:** PASSIVE, opóźnienie: 1 tura.
- Po jednej turze pion detonuje i niszczy wszystkie figury w promieniu jednego pola, także sojusznicze.

### Kamikaze z opóźnieniem — 2 tury

- **Wymagana figura:** pion. **Oznaczenia:** PASSIVE, opóźnienie: 2 tury.
- Po dwóch turach pion detonuje i niszczy wszystkie figury w promieniu jednego pola, także sojusznicze.

### Szermierz

- **Wymagana figura:** pion. **Oznaczenie:** BUFF.
- Pion może poruszać się na boki.

### Wskrzeszenie piona

- **Wymagana figura:** król.
- Wskrześ zbitego przez przeciwnika piona i umieść go na pustym polu w promieniu jednego pola od króla.

### Wskrzeszenie skoczka

- **Wymagana figura:** król.
- Wskrześ zbitego przez przeciwnika skoczka i umieść go na pustym polu w promieniu jednego pola od króla.

### Wskrzeszenie gońca

- **Wymagana figura:** król.
- Wskrześ zbitego przez przeciwnika gońca i umieść go na pustym polu w promieniu jednego pola od króla.

### Wskrzeszenie wieży

- **Wymagana figura:** król.
- Wskrześ zbitą przez przeciwnika wieżę i umieść ją na pustym polu w promieniu jednego pola od króla.

### Wskrzeszenie hetmana

- **Wymagana figura:** król.
- Wskrześ zbitego przez przeciwnika hetmana i umieść go na pustym polu w promieniu jednego pola od króla.

### Rzut wieżą

- **Wymagana figura:** wieża. **Oznaczenia:** efekt obowiązkowy; ogłuszenie po użyciu: 2 tury.
- Wieża porusza się do końca planszy, zbijając wszystkie figury na drodze, również własne. Po ruchu jest ogłuszona na dwie tury.

### Awans piona: skoczek

- **Wymagana figura:** pion. **Ogłuszenie po użyciu:** 1 tura.
- Awansuj piona na skoczka; pion zostaje ogłuszony na jedną turę.

### Awans piona: goniec

- **Wymagana figura:** pion. **Ogłuszenie po użyciu:** 2 tury.
- Awansuj piona na gońca; pion zostaje ogłuszony na dwie tury.

### Awans piona: wieża

- **Wymagana figura:** pion. **Ogłuszenie po użyciu:** 3 tury.
- Awansuj piona na wieżę; pion zostaje ogłuszony na trzy tury.

### Awans piona: hetman

- **Wymagana figura:** pion. **Ogłuszenie po użyciu:** 4 tury.
- Awansuj piona na hetmana; pion zostaje ogłuszony na cztery tury.

### Awans skoczka: goniec

- **Wymagana figura:** skoczek. **Ogłuszenie po użyciu:** 1 tura.
- Awansuj skoczka na gońca; skoczek zostaje ogłuszony na jedną turę.

### Awans skoczka: wieża

- **Wymagana figura:** skoczek. **Ogłuszenie po użyciu:** 2 tury.
- Awansuj skoczka na wieżę; skoczek zostaje ogłuszony na dwie tury.

### Awans skoczka: hetman

- **Wymagana figura:** skoczek. **Ogłuszenie po użyciu:** 3 tury.
- Awansuj skoczka na hetmana; skoczek zostaje ogłuszony na trzy tury.

### Awans gońca: wieża

- **Wymagana figura:** goniec. **Ogłuszenie po użyciu:** 1 tura.
- Awansuj gońca na wieżę; goniec zostaje ogłuszony na jedną turę.

### Awans gońca: hetman

- **Wymagana figura:** goniec. **Ogłuszenie po użyciu:** 2 tury.
- Awansuj gońca na hetmana; goniec zostaje ogłuszony na dwie tury.

### Awans wieży: hetman

- **Wymagana figura:** wieża. **Ogłuszenie po użyciu:** 1 tura.
- Awansuj wieżę na hetmana; wieża zostaje ogłuszona na jedną turę.

### Powrót na start

- **Wymagana figura:** dowolna. **Oznaczenie:** wielokrotnego użytku, 1–3 użycia.
- Przenieś wybraną figurę na jej pole startowe, jeśli jest wolne. Ten ruch nie zbija figur.

### Teleportacja

- **Wymagana figura:** dowolna.
- Zamień miejscami swoją figurę z dowolną inną figurą.

### Podwójny ruch

- **Wymagana figura:** dowolna. **Oznaczenie:** wielokrotnego użytku, 1–3 użycia.
- Wykonaj dwa ruchy tą samą figurą w jednej turze.
