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
- Selftest, no phone or Spectrum connection: `bun src/index.ts --selftest`.

## Where to go next

- [Spectrum docs](https://photon.codes/docs/spectrum-ts)
- Edit `src/index.ts` to replace the echo loop with real agent logic.
- Add more providers from `spectrum-ts/providers/*`.
