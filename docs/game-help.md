# Instrukcja gry Chess NEXT

## Cel gry

- Białe wykonują pierwszy ruch, potem gracze wykonują akcje na zmianę.
- Wygrywa gracz, który zbije lub usunie króla przeciwnika.
- Gra nie używa szacha, mata ani pata: król może wejść na atakowane pole, a ruch nie jest odrzucany z powodu zagrożenia króla.
- Ruchy figur mogą być zmieniane przez zaklęcia. Dostępne pola są podświetlane po wybraniu figury.

## Awans piona

- Gdy pion dotrze do przeciwległego krańcowego wiersza, natychmiast wybierz w oknie pop-up hetmana, wieżę, gońca lub skoczka.
- Awans w ten sposób nie wymaga karty i nie nakłada ogłuszenia. Karty awansu nadal pozwalają zmieniać typ figur także poza krańcowym wierszem, zgodnie z opisem karty.

## Sterowanie

- Kliknij własną figurę, a następnie podświetlone pole, aby wykonać ruch.
- Kliknij kartę w swojej ręce, a potem wybierz figurę lub pole wskazane przez jej opis.
- Każdy opis karty podaje kolejne kliknięcia po wybraniu karty. Prawidłowe pola są podświetlane.
- Niektóre karty wymagają kilku kliknięć, na przykład wskazania wieży, piona i pola docelowego dla trebusza.
- Ruch na pole z kartą planszową zbiera ją do ręki, o ile gracz nie ma już maksymalnej liczby kart.
- `Esc` otwiera lub zamyka menu pauzy. `Spacja` rozpoczyna partię od nowa.
- Podczas animacji ruchu lub karty wejście gracza jest chwilowo wstrzymane.

## Oznaczenia kart

- :PASSIVE: PASSIVE — efekt pasywny: karta zostaje przypisana do figury i uruchamia swój efekt zgodnie z opisem. Zastosowanie karty kończy turę.
- :BUFF: BUFF — wzmocnienie: zmienia sposób poruszania się figury. Zastosowanie nie kończy tury, więc przed ruchem można nałożyć kilka wzmocnień.
- :REUSABLE: REUSABLE — wielokrotnego użytku: liczba przy ikonie oznacza pozostałe użycia. Karta zostaje w ręce, dopóki nie zużyje ostatniego.
- :DELAY_BEFORE_USE: DELAY_BEFORE_USE — opóźnienie: liczba przy ikonie oznacza liczbę tur przed uruchomieniem efektu.
- :STUN_AFTER_USE: STUN_AFTER_USE — ogłuszenie: liczba przy ikonie oznacza długość ogłuszenia figury po użyciu karty. Ogłuszona figura nie może się poruszać ani otrzymywać zaklęć.
- **MANDATORY — efekt obowiązkowy:** nie ma osobnej ikonki. Taki efekt ma pierwszeństwo i zatrzymuje łączenie kolejnych modyfikatorów ruchu tej figury.
- Karta może mieć kilka oznaczeń naraz; liczby pod ikonami dotyczą tej ikony.

## Karty zaklęć

### Skok do przodu

- **Wymagana figura:** pion. **Oznaczenia:** :REUSABLE: 1–3 użycia.
- Pion może wykonać ruch o dwa pola do przodu.
- **Użycie:** wybierz kartę, kliknij własnego piona, a następnie podświetlone pole docelowe.

### Ruch do tyłu

- **Wymagana figura:** pion. **Oznaczenie:** :BUFF:
- Pion może cofać się o jedno pole i zbijać po skosie do tyłu.
- **Użycie:** wybierz kartę i kliknij własnego piona, aby nałożyć wzmocnienie. Następnie wybierz piona ponownie i kliknij jedno z nowych legalnych pól ruchu.

### Pułapka runiczna

- **Wymagana figura:** skoczek.
- Postaw runę na pustym sąsiednim polu. Pierwsza figura, która na nią wejdzie lub przez nią przejdzie, ginie. Runa znika po pięciu kolejnych turach właściciela albo natychmiast po zbiciu skoczka, który ją postawił.
- **Użycie:** wybierz kartę, kliknij własnego skoczka, a następnie puste, podświetlone pole obok niego.

### Oficer

- **Wymagana figura:** pion. **Oznaczenie:** :PASSIVE:
- Sąsiednie sojusznicze piony naśladują ruch oficera, korzystając z jego aktywnych efektów pasywnych.
- **Użycie:** wybierz kartę i kliknij własnego piona, który ma zostać oficerem. Zastosowanie kończy turę.

### Trebusz

- **Wymagana figura:** wieża. **Oznaczenia:** :REUSABLE: 1–2 użycia; :STUN_AFTER_USE: 1 tura.
- Wystrzel piona sąsiadującego z wieżą na puste pole w promieniu pięciu pól. Wieża zostaje ogłuszona na jedną turę.
- **Użycie:** wybierz kartę, kliknij własną wieżę, kliknij piona do wystrzelenia, a potem kliknij podświetlone puste pole docelowe.

### Rekrut

- **Wymagana figura:** dowolna. **Oznaczenie:** :REUSABLE: 1–5 użyć.
- Stwórz piona na pustym polu linii startowej: linii 1 dla białych lub linii 8 dla czarnych.
- **Użycie:** wybierz kartę i kliknij jedno z podświetlonych pustych pól na swojej linii startowej.

### Przesunięcie skoczka

- **Wymagana figura:** skoczek. **Oznaczenie:** :REUSABLE: 1–3 użycia.
- Skoczek może poruszyć się o jedno pole w dowolnym kierunku.
- **Użycie:** wybierz kartę, kliknij własnego skoczka, a następnie wybierz jedno z podświetlonych pól.

### Wystrzał wieży

- **Wymagana figura:** wieża.
- Wieża może przeskakiwać nad sojuszniczymi figurami, ale nie może ich zbijać.
- **Użycie:** wybierz kartę, kliknij własną wieżę, a następnie kliknij legalne pole docelowe, także za sojusznikiem.

### Wystrzał hetmana

- **Wymagana figura:** hetman. **Oznaczenie:** efekt obowiązkowy.
- Hetman może przeskakiwać nad sojusznikami do czterech pól, ale nie może zbijać.
- **Użycie:** wybierz kartę, kliknij własnego hetmana, a następnie kliknij legalne pole docelowe.

### Kamikaze

- **Wymagana figura:** pion. **Oznaczenie:** :PASSIVE:
- Pion detonuje i niszczy wszystkie figury w promieniu jednego pola, także sojusznicze.
- **Użycie:** wybierz kartę i kliknij własnego piona, aby natychmiast go zdetonować.

### Kamikaze z opóźnieniem — 1 tura

- **Wymagana figura:** pion. **Oznaczenia:** :PASSIVE: :DELAY_BEFORE_USE: 1 tura.
- Po jednej turze pion detonuje i niszczy wszystkie figury w promieniu jednego pola, także sojusznicze.
- **Użycie:** wybierz kartę i kliknij własnego piona. Detonacja nastąpi po jednej turze.

### Kamikaze z opóźnieniem — 2 tury

- **Wymagana figura:** pion. **Oznaczenia:** :PASSIVE: :DELAY_BEFORE_USE: 2 tury.
- Po dwóch turach pion detonuje i niszczy wszystkie figury w promieniu jednego pola, także sojusznicze.
- **Użycie:** wybierz kartę i kliknij własnego piona. Detonacja nastąpi po dwóch turach.

### Szermierz

- **Wymagana figura:** pion. **Oznaczenie:** :BUFF:
- Pion może poruszać się na boki.
- **Użycie:** wybierz kartę i kliknij własnego piona, aby nałożyć wzmocnienie. Następnie wybierz piona ponownie i kliknij jedno z nowych legalnych pól ruchu.

### Wskrzeszenie piona

- **Wymagana figura:** król.
- Wskrześ zbitego przez przeciwnika piona i umieść go na pustym polu w promieniu jednego pola od króla.
- **Użycie:** wybierz kartę, kliknij zbitego piona przeciwnika w panelu zbitych figur, a potem kliknij podświetlone puste pole obok swojego króla.

### Wskrzeszenie skoczka

- **Wymagana figura:** król.
- Wskrześ zbitego przez przeciwnika skoczka i umieść go na pustym polu w promieniu jednego pola od króla.
- **Użycie:** wybierz kartę, kliknij zbitego skoczka przeciwnika w panelu zbitych figur, a potem kliknij podświetlone puste pole obok swojego króla.

### Wskrzeszenie gońca

- **Wymagana figura:** król.
- Wskrześ zbitego przez przeciwnika gońca i umieść go na pustym polu w promieniu jednego pola od króla.
- **Użycie:** wybierz kartę, kliknij zbitego gońca przeciwnika w panelu zbitych figur, a potem kliknij podświetlone puste pole obok swojego króla.

### Wskrzeszenie wieży

- **Wymagana figura:** król.
- Wskrześ zbitą przez przeciwnika wieżę i umieść ją na pustym polu w promieniu jednego pola od króla.
- **Użycie:** wybierz kartę, kliknij zbitą wieżę przeciwnika w panelu zbitych figur, a potem kliknij podświetlone puste pole obok swojego króla.

### Wskrzeszenie hetmana

- **Wymagana figura:** król.
- Wskrześ zbitego przez przeciwnika hetmana i umieść go na pustym polu w promieniu jednego pola od króla.
- **Użycie:** wybierz kartę, kliknij zbitego hetmana przeciwnika w panelu zbitych figur, a potem kliknij podświetlone puste pole obok swojego króla.

### Rzut wieżą

- **Wymagana figura:** wieża. **Oznaczenia:** efekt obowiązkowy; :STUN_AFTER_USE: 2 tury.
- Wieża porusza się do końca planszy, zbijając wszystkie figury na drodze, również własne. Po ruchu jest ogłuszona na dwie tury.
- **Użycie:** wybierz kartę, kliknij własną wieżę, a następnie wybierz podświetlone pole docelowe na końcu jej trasy.

### Awans piona: skoczek

- **Wymagana figura:** pion. **Oznaczenie:** :STUN_AFTER_USE: 1 tura.
- Awansuj piona na skoczka; pion zostaje ogłuszony na jedną turę.
- **Użycie:** wybierz kartę i kliknij własnego piona.

### Awans piona: goniec

- **Wymagana figura:** pion. **Oznaczenie:** :STUN_AFTER_USE: 2 tury.
- Awansuj piona na gońca; pion zostaje ogłuszony na dwie tury.
- **Użycie:** wybierz kartę i kliknij własnego piona.

### Awans piona: wieża

- **Wymagana figura:** pion. **Oznaczenie:** :STUN_AFTER_USE: 3 tury.
- Awansuj piona na wieżę; pion zostaje ogłuszony na trzy tury.
- **Użycie:** wybierz kartę i kliknij własnego piona.

### Awans piona: hetman

- **Wymagana figura:** pion. **Oznaczenie:** :STUN_AFTER_USE: 4 tury.
- Awansuj piona na hetmana; pion zostaje ogłuszony na cztery tury.
- **Użycie:** wybierz kartę i kliknij własnego piona.

### Awans skoczka: goniec

- **Wymagana figura:** skoczek. **Oznaczenie:** :STUN_AFTER_USE: 1 tura.
- Awansuj skoczka na gońca; skoczek zostaje ogłuszony na jedną turę.
- **Użycie:** wybierz kartę i kliknij własnego skoczka.

### Awans skoczka: wieża

- **Wymagana figura:** skoczek. **Oznaczenie:** :STUN_AFTER_USE: 2 tury.
- Awansuj skoczka na wieżę; skoczek zostaje ogłuszony na dwie tury.
- **Użycie:** wybierz kartę i kliknij własnego skoczka.

### Awans skoczka: hetman

- **Wymagana figura:** skoczek. **Oznaczenie:** :STUN_AFTER_USE: 3 tury.
- Awansuj skoczka na hetmana; skoczek zostaje ogłuszony na trzy tury.
- **Użycie:** wybierz kartę i kliknij własnego skoczka.

### Awans gońca: wieża

- **Wymagana figura:** goniec. **Oznaczenie:** :STUN_AFTER_USE: 1 tura.
- Awansuj gońca na wieżę; goniec zostaje ogłuszony na jedną turę.
- **Użycie:** wybierz kartę i kliknij własnego gońca.

### Awans gońca: hetman

- **Wymagana figura:** goniec. **Oznaczenie:** :STUN_AFTER_USE: 2 tury.
- Awansuj gońca na hetmana; goniec zostaje ogłuszony na dwie tury.
- **Użycie:** wybierz kartę i kliknij własnego gońca.

### Awans wieży: hetman

- **Wymagana figura:** wieża. **Oznaczenie:** :STUN_AFTER_USE: 1 tura.
- Awansuj wieżę na hetmana; wieża zostaje ogłuszona na jedną turę.
- **Użycie:** wybierz kartę i kliknij własną wieżę.

### Powrót na start

- **Wymagana figura:** dowolna. **Oznaczenie:** :REUSABLE: 1–3 użycia.
- Przenieś wybraną figurę na jej pole startowe, jeśli jest wolne. Ten ruch nie zbija figur.
- **Użycie:** wybierz kartę, kliknij własną figurę, a następnie kliknij podświetlone, wolne pole startowe tego samego typu i koloru.

### Teleportacja

- **Wymagana figura:** dowolna.
- Zamień miejscami swoją figurę z dowolną inną figurą.
- **Użycie:** wybierz kartę, kliknij własną figurę, a następnie kliknij drugą figurę, z którą ma zamienić się miejscami.

### Podwójny ruch

- **Wymagana figura:** dowolna. **Oznaczenie:** :REUSABLE: 1–3 użycia.
- Wykonaj dwa ruchy tą samą figurą w jednej turze.
- **Użycie:** wybierz kartę, kliknij własną figurę, wykonaj pierwszy ruch, a następnie kliknij drugie podświetlone pole dla tej samej figury.
