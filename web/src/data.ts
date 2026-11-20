// Demo data for the design. People come from tools/profiles.json and spaghetti
// from agent/product_cache/spaghetti.json. The rest of the menu's products have
// no shared data yet, so they stay as placeholders below until the shopper
// agent supplies them. Shapes follow contracts/models.py.

import profiles from "../../tools/profiles.json";
import spaghettiCache from "../../agent/product_cache/spaghetti.json";

export type NeedKind = "must" | "flex";
export type Need = { label: string; kind: NeedKind };

type Profile = { id: string; name: string; restrictions: string[]; allergens: string[]; cuisines: string[]; contact: string | null; preferences?: string[] };

export type Person = {
  id: string;
  name: string;
  role: "host" | "guest";
  needs: Need[];
  reply: "replied" | "waiting";
  replyAfterMs: number; // how long the simulated reply takes on the agents screen
  connection: "accepted" | "pending" | "none";
  scope: string[]; // what this person lets the host's agent use
};

// Who is who in the demo story. Profiles come from tools/profiles.json; these
// ids only pick which profile plays which part.
export const HOST_ID = "g4"; // Ryan hosts; the other five are guests
export const ROLE = {
  vegan: "g1",
  noSpicy: "g2",
  noMushroom: "g3",
  turnsVegan: "g5", // the "one more guest is vegan" change
};

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

// Restrictions and allergens are hard requirements; nothing marks them flexible
// yet, so the safe default is must-have. Preferences are soft.
const toNeeds = (p: Profile): Need[] => [
  ...p.restrictions.map((r) => ({ label: cap(r), kind: "must" as const })),
  ...p.allergens.map((a) => ({ label: `${cap(a)} allergy`, kind: "must" as const })),
  ...(p.preferences ?? []).map((x) => ({ label: cap(x), kind: "flex" as const })),
];

export const PEOPLE: Person[] = (profiles as Profile[])
  .map((p, i) => ({
    id: p.id,
    name: p.name,
    role: p.id === HOST_ID ? ("host" as const) : ("guest" as const),
    needs: toNeeds(p),
    reply: p.id === HOST_ID ? ("replied" as const) : ("waiting" as const),
    replyAfterMs: 1200 + i * 800,
    connection: "accepted" as const,
    scope: ["Dietary profile"],
  }))
  .sort((a, b) => (a.role === "host" ? -1 : b.role === "host" ? 1 : 0));

export const nameOf = (id: string) => PEOPLE.find((p) => p.id === id)?.name ?? id;
export const HOST = nameOf(HOST_ID);

type CachedProduct = { id: string; name: string; source: string; price: number; pack_size: string; ingredients: string[] };
// Real listings from agent/product_cache/spaghetti.json (pulled by the data tools).
const SPAGHETTI = (spaghettiCache as CachedProduct[]).slice(0, 1).map((c) => ({ id: c.id, name: c.name, source: c.source, price: c.price, pack: c.pack_size, ingredients: c.ingredients }));

export type Ingredient = {
  id: string;
  name: string;
  need: string;
  pantry?: { have: string; covers: boolean }; // host must confirm before it counts
  productId?: string;
  qtyIfPantry: number; // packs to buy when the pantry amount is confirmed
  qtyIfNot: number; // packs to buy when it is not
};

export const INGREDIENTS: Ingredient[] = [
  { id: "spaghetti", name: "Spaghetti", need: "600 g", pantry: { have: "500 g", covers: false }, productId: SPAGHETTI[0].id, qtyIfPantry: 1, qtyIfNot: 2 },
  { id: "oil", name: "Olive oil", need: "150 ml", pantry: { have: "about 400 ml", covers: true }, productId: "a-oil", qtyIfPantry: 0, qtyIfNot: 1 },
  { id: "salt", name: "Salt", need: "2 tsp", pantry: { have: "a full shaker", covers: true }, productId: "a-salt", qtyIfPantry: 0, qtyIfNot: 1 },
  { id: "tomato", name: "Crushed tomatoes", need: "2 cans", productId: "b-tomato", qtyIfPantry: 2, qtyIfNot: 2 },
  { id: "chickpea", name: "Chickpeas", need: "3 cans", productId: "a-chickpea", qtyIfPantry: 3, qtyIfNot: 3 },
  { id: "garlic", name: "Garlic", need: "6 cloves", productId: "a-garlic", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "basil", name: "Fresh basil", need: "1 bunch", productId: "b-basil", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "greens", name: "Spring mix", need: "300 g", productId: "b-salad", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "cucumber", name: "Cucumber", need: "2", productId: "a-cucumber", qtyIfPantry: 2, qtyIfNot: 2 },
  { id: "cherry", name: "Cherry tomatoes", need: "1 pint", productId: "a-cherry", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "lemon", name: "Lemons", need: "3", productId: "a-lemon", qtyIfPantry: 3, qtyIfNot: 3 },
  { id: "mustard", name: "Dijon mustard", need: "1 tbsp", productId: "b-mustard", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "ciabatta", name: "Ciabatta", need: "1 loaf", productId: "b-ciabatta", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "berries", name: "Strawberries", need: "1 lb", productId: "a-straw", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "grapes", name: "Grapes", need: "2 lb", productId: "b-grapes", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "pineapple", name: "Pineapple", need: "1", productId: "a-pineapple", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "chili", name: "Chili flakes", need: "1 small jar", productId: "a-chili", qtyIfPantry: 1, qtyIfNot: 1 },
  { id: "water", name: "Sparkling water", need: "12 cans", productId: "a-soda6", qtyIfPantry: 2, qtyIfNot: 2 },
];

export type Product = {
  id: string;
  name: string;
  source: string;
  price: number;
  pack: string;
  ingredients: string[] | null; // null = list missing, show as needs confirmation
};

const p = (id: string, name: string, source: Product["source"], price: number, pack: string, ingredients: string[] | null): Product => ({ id, name, source, price, pack, ingredients });

export const PRODUCTS: Record<string, Product> = Object.fromEntries(
  [
    ...SPAGHETTI,
    p("a-oil", "Olive oil", "Store A", 7.99, "500 ml", ["olive oil"]),
    p("a-salt", "Sea salt", "Store A", 1.49, "26 oz", ["salt"]),
    p("b-tomato", "Crushed tomatoes", "Store B", 2.49, "28 oz can", ["tomato", "salt", "citric acid"]),
    p("a-chickpea", "Chickpeas", "Store A", 1.19, "15 oz can", ["chickpeas", "water", "salt"]),
    p("a-garlic", "Garlic", "Store A", 0.79, "1 bulb", ["garlic"]),
    p("b-basil", "Fresh basil", "Store B", 2.49, "0.75 oz", ["basil"]),
    p("b-salad", "Spring mix", "Store B", 3.49, "11 oz", ["lettuce", "spinach"]),
    p("a-cucumber", "Cucumber", "Store A", 0.89, "each", ["cucumber"]),
    p("a-cherry", "Cherry tomatoes", "Store A", 3.29, "1 pint", ["tomato"]),
    p("a-lemon", "Lemon", "Store A", 0.69, "each", ["lemon"]),
    p("b-mustard", "Dijon mustard", "Store B", 2.19, "8 oz", null),
    p("b-ciabatta", "Ciabatta loaf", "Store B", 3.49, "14 oz", ["wheat flour", "water", "olive oil", "yeast", "salt"]),
    p("a-straw", "Strawberries", "Store A", 3.99, "1 lb", ["strawberries"]),
    p("b-grapes", "Red grapes", "Store B", 4.98, "2 lb", ["grapes"]),
    p("a-pineapple", "Pineapple", "Store A", 2.99, "each", ["pineapple"]),
    p("b-gfpasta", "Gluten-free spaghetti", "Store B", 3.49, "12 oz", ["corn flour", "rice flour"]),
    p("a-chili", "Chili flakes", "Store A", 2.99, "1.3 oz", ["red chili pepper"]),
    p("a-soda6", "Sparkling water", "Store A", 3.98, "6-pack", ["carbonated water"]),
  ].map((x) => [x.id, x]),
);

// Simulated delivery fees per store; unknown stores show $0 and the "Simulated" tag.
export const DELIVERY: Record<string, number> = { "Store A": 5.99, "Store B": 0 };

export const money = (n: number) => `$${n.toFixed(2)}`;

// How each person gets their invite. profiles.json has no contact details yet,
// so this is demo data: "app" means they have the app, otherwise text or WhatsApp.
export type Channel = "app" | "text" | "whatsapp";
export const CHANNEL: Record<string, Channel> = { g1: "app", g2: "text", g3: "whatsapp", g5: "app", g6: "text" };
export const CHANNEL_LABEL: Record<Channel, string> = { app: "In the app", text: "By text", whatsapp: "On WhatsApp" };

// Times used by the scheduling demo.
export type Slot = { id: string; label: string; short: string };
export const SLOTS: Record<string, Slot> = {
  sat7: { id: "sat7", label: "Saturday, Nov 28 at 7 PM", short: "Saturday at 7" },
  sun6: { id: "sun6", label: "Sunday, Nov 29 at 6 PM", short: "Sunday at 6" },
  fri730: { id: "fri730", label: "Friday, Nov 27 at 7:30 PM", short: "Friday at 7:30" },
};
