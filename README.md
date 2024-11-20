## Usage

### Configuring your frontend

For Discord, create a bot and give it the `application.commands` and `bot` scopes.
It will also need to be able to manage channels, expressions, messages, threads, and be able to read message history.

### Running the program

1. `poetry install`

2. Create a `.env` file and populate it with:

- `OPENAI_API_KEY=<...>` - an OpenAI API key
- `ANTHROPIC_API_KEY=<...>` - an Anthropic API key
- `DISCORD_TOKEN=<...>` - the token of your Discord bot, if using Discord

3. Create a config file. The one in `configs/example.toml` is a good starting point.

4. `poetry run python fun_game/main.py --config <path/to/your_config.toml>`

---

## TODO

- [ ] Refactor bidding into BiddingManager
- [ ] Improve JSON outputs
- [ ] Add optional seed param to start command
- [ ] Add score counting
- [ ] Refactor shared inventory
