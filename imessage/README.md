# imessage

A [Spectrum](https://photon.codes/docs/spectrum-ts) project. Wired with: imessage.

## Environment

Before running, open `.env` and fill in the values:

From your project Settings on the [Photon dashboard](https://app.photon.codes):

- `PROJECT_ID`
- `PROJECT_SECRET`

## Run

```sh
bun install
bun start
```

## Bridge

- What it does: forwards each inbound iMessage text to `POST $API_URL/messages` (`{sender, text}` -> `{reply}`) and sends the reply back; interim "On it" after 3 s, error message after a failure or 150 s.
- Run: `bun start` (needs `PROJECT_ID`, `PROJECT_SECRET`; optional `API_URL`).
- Outbox: every `OUTBOX_POLL_MS` (default 3000) the bot calls `GET $API_URL/outbox` (`{messages: [{sender, text}]}`, server removes what it returns) and texts each message to that sender; 404 or errors are treated as empty (logged at most once a minute), and senders the bot has never heard from are dropped with `OUTBOX no conversation for <last 4>`.
- Senders are remembered in memory and in `.outbox-senders.log` (gitignored), so after a restart the bot reopens the DM with `imessage(app).space.create(user)`; shared-plan recipients must be registered Photon project users.
- Selftest, no phone or Spectrum connection: `bun src/index.ts --selftest`.

## Where to go next

- [Spectrum docs](https://photon.codes/docs/spectrum-ts)
- Edit `src/index.ts` to replace the echo loop with real agent logic.
- Add more providers from `spectrum-ts/providers/*`.
