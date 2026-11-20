// Recipes for the demo menu, written for six. These are what the agent hands
// the host along with the shopping list. All four are vegan, no mushrooms, no chili.

export type Recipe = { id: string; name: string; course: string; minutes: number; serves: number; ingredients: string[]; steps: string[] };

export const RECIPES: Recipe[] = [
  {
    id: "main",
    name: "Tomato and chickpea pasta",
    course: "Main",
    minutes: 35,
    serves: 6,
    ingredients: ["600 g spaghetti", "2 cans (28 oz) crushed tomatoes", "3 cans (15 oz) chickpeas, drained", "6 garlic cloves, sliced", "4 tbsp olive oil", "1 bunch fresh basil", "Salt"],
    steps: [
      "Bring a large pot of well-salted water to a boil.",
      "Warm the olive oil in a wide pan over medium heat. Add the garlic and cook until just golden, about 2 minutes.",
      "Add the chickpeas and cook for 5 minutes, stirring, until they start to crisp.",
      "Pour in the crushed tomatoes, season with salt and simmer for 15 minutes.",
      "Cook the spaghetti until al dente. Save a cup of the cooking water, then drain.",
      "Toss the pasta into the sauce, loosening with pasta water. Tear the basil over the top and serve.",
    ],
  },
  {
    id: "salad",
    name: "Green salad with lemon dressing",
    course: "Side",
    minutes: 15,
    serves: 6,
    ingredients: ["300 g spring mix", "2 cucumbers, sliced", "1 pint cherry tomatoes, halved", "2 lemons", "4 tbsp olive oil", "1 tbsp Dijon mustard (no honey)", "Salt"],
    steps: [
      "Whisk the juice of 2 lemons with the olive oil, mustard and a pinch of salt.",
      "Put the greens, cucumber and tomatoes in a large bowl.",
      "Dress just before serving so the leaves stay crisp.",
    ],
  },
  {
    id: "bread",
    name: "Warm ciabatta",
    course: "Side",
    minutes: 10,
    serves: 6,
    ingredients: ["1 ciabatta loaf", "Olive oil for dipping", "Salt"],
    steps: ["Warm the loaf in a 200 °C (400 °F) oven for 8 minutes.", "Slice and serve with a small bowl of olive oil and a pinch of salt."],
  },
  {
    id: "fruit",
    name: "Fruit platter",
    course: "Dessert",
    minutes: 15,
    serves: 6,
    ingredients: ["1 lb strawberries", "2 lb red grapes", "1 pineapple", "1 lemon"],
    steps: ["Hull and halve the strawberries. Cut the grapes into small bunches.", "Peel, core and slice the pineapple.", "Arrange on a platter and squeeze over a little lemon."],
  },
];

export const ON_THE_SIDE = "Chili flakes in a small bowl, for anyone who wants heat. Keep them out of every pot.";
