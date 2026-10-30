Generuj komunikaty commitów w formacie Conventional Commits z gitmoji. Używaj dokładnie tej struktury:

```text
<typ>[opcjonalny zakres]: <gitmoji> <opis>

[opcjonalne uzasadnienie]
```

Przykłady:
- `feat(auth): :sparkles: dodaj walidację logowania`
- `fix(api): :bug: napraw przekroczenie limitu czasu pobierania danych użytkownika`
- `docs: :memo: zaktualizuj instrukcję instalacji w README`
- `docs: :bookmark: dodaj komentarze JSDoc do komponentu media`
- `style: :art: sformatuj kod zgodnie z regułami lintowania`
- `refactor: :recycle: przebuduj wykrywanie platformy wideo`

Typ musi być jednym z poniższych:
- `feat`: nowa funkcja
- `fix`: poprawka błędu
- `docs`: zmiany w dokumentacji, w tym aktualizacje README, komentarze JSDoc i dokumentacja kodu
- `style`: zmiany nie wpływające na działanie kodu, takie jak formatowanie czy białe znaki
- `refactor`: zmiany w strukturze kodu, które nie naprawiają błędów ani nie dodają funkcji
- `perf`: zmiana kodu poprawiająca wydajność
- `test`: dodanie lub poprawienie testów
- `build`: zmiany dotyczące systemu budowania lub zależności
- `ci`: zmiany konfiguracji CI, na przykład GitHub Actions lub Jenkins
- `chore`: pozostałe zmiany, które nie modyfikują plików źródłowych ani testowych
- `revert`: cofnięcie wcześniejszego commita

Zawsze umieszczaj pasujący kod gitmoji na początku opisu. Dobierz gitmoji do rodzaju zmiany.

Ważne: przy dodawaniu lub zmianie JSDoc używaj typu `docs` (z `:bulb:` lub `:memo:`), a nie `refactor`.

W uzasadnieniu:
- Przy kilku punktach używaj listy punktowanej (`*`).
- Wyjaśnij, dlaczego zmiana była potrzebna.
- Podaj istotny kontekst lub szczegóły techniczne.

Zadbaj o profesjonalny ton i jasne przedstawienie celu commita.

Pisz po polsku. Jeśli zmiany można jasno określić, niech opis będzie złożony z maksymalnie 3 zdań. Jeśli commit jest bardziej złożony, opisz generalne jego założenia wraz z gitmoji, a szczegóły wypunktuj poniżej.