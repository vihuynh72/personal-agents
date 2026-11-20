# web/ — Gathering front end

First sign-in: sign in (Google or email), connect Google Calendar (free/busy
only, or skip), then pick allergies, diets and things you'd rather avoid. The
food profile is saved in the backend's `GuestProfile` shape. Later sign-ins with
the same account go straight to the chat ("Welcome back"); the profile can be
edited from the "Food profile" button in the top bar.

Then the host talks to their agent by typing or by voice:

1. "I'm hosting a dinner" -> the agent asks who to invite (friends with the app
   get it in the app; others by text or WhatsApp).
2. The host either picks the day and time, or asks the agent to find a time
   that works; the agent asks everyone's agent when they're free and ranks times.
3. The invitation goes out. Invitees answer Going, Can't make it, or Suggest
   another time. If someone suggests a time, the agent checks everyone's
   calendar and offers the host a one-tap move (or keep); only people who had
   already said yes are asked to reconfirm. The host always decides.
4. Once the time is locked, the agents of the people coming share dietary needs,
   and the agent says "Let's make this": menu, shopping list scaled to the
   number of people, recipes, and one Pay with Stripe button.

```
npm install
npm run dev        # http://localhost:5173
npm run build      # static site in dist/
```

## Where things live

| File | What it is |
|---|---|
| `src/Onboarding.tsx` | Sign-in and the Google Calendar connect screen (both simulated) |
| `src/App.tsx` | The conversation, its cards (table, menu, list and recipes, receipt) and the "How I decided" drawer (audit trail) |
| `src/voice.ts` | Talk and read-aloud using the browser's built-in speech (no key needed; Chrome, Edge, Safari) |
| `src/data.ts` | People from `tools/profiles.json`, spaghetti from `agent/product_cache/spaghetti.json`, placeholder products for the rest of the menu |
| `src/recipes.ts` | Recipes for the menu, written for six |
| `src/api.ts` | The only link to `agent/`. Simulated for now |

## Going live

Set `VITE_API_URL` to the backend (e.g. the Railway URL) and `src/api.ts` uses it:

| Front end | Backend |
|---|---|
| Sign-in looks up the profile | `GET /profiles/{id}` (id = the email) |
| Save food profile | `PUT /profiles/{id}` with `allergens`, `restrictions`, `preferences` |
| Connect Google Calendar | browser goes to `GET /connect/google?sender={id}`; needs `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on the server |
| Chat | `POST /messages {sender, text}` -> `{reply}` (still scripted in `App.tsx`) |
| Pay | the backend's `/cart/{gid}` page with Stripe test mode |

Without `VITE_API_URL` everything is simulated in the browser: accounts are kept
in localStorage ("Forget saved accounts" on the sign-in screen clears them).
