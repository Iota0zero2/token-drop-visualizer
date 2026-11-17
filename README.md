# Token Drop Visualizer

A dark-mode desktop app that visualizes the odds of a party getting a token from chests (default drop rate: 1 in 137,000).

When one party member gets the token, the whole party gets it, so every number is for the whole party.

## Run

```
python3 token_drop.py
```

It only needs Python 3 with tkinter. There are no other dependencies.

## Features

- Sliders for players per party, chests per player per game, game length and hours played per day. Every chart updates as you drag.
- Stat cards: chance per game and per day, time until a 50% or 90% chance, and the average wait.
- A cumulative probability graph with 50%, 90% and 99% markers. Hover over it to see the odds at any point.
- Odds for each time frame, from one chest up to one year, plus a clickable luck-meter gauge.
- "Simulate a grind" rolls a random drop time.
- Settings (Cmd+,): edit each slider's min, max and step, and the drop rate. These are saved to `settings.json`.

## License

MIT. See [LICENSE](LICENSE).
