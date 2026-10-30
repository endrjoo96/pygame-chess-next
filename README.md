# pygame-chess
Chess game written in python with the pygame library.

## Run mode

Set `mode` in `run.properties` to `DEBUG` for uniform random card selection, or
`PROD` to select cards using their configured rarity weights.

The AI search limits can also be adjusted in `run.properties`:
`ai.search.max_depth` sets the maximum search depth in half-moves, and
`ai.search.time_limit_seconds` sets the time budget in seconds for choosing a move.
The AI evaluates candidate moves in separate processes, using up to all available
logical CPU cores; the time budget applies to the whole search.

## Game Menu
![menu](https://user-images.githubusercontent.com/24194821/57589722-cf907c00-74eb-11e9-9318-822abd6c9942.png)

## Gameplay
![game](https://user-images.githubusercontent.com/24194821/57589721-cf907c00-74eb-11e9-8def-bf4782315ed9.png)

## Winner Menu
![checkmate](https://user-images.githubusercontent.com/24194821/57589723-cf907c00-74eb-11e9-8b42-aef703c3e1f8.png)
