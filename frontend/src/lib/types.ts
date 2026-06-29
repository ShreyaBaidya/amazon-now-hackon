export type Product = {
  id: string;
  name: string;
  brand: string;
  price: number;
  size: string;
  category: string;
  image: string;
  dietary_tags: string[];
  allergen_tags: string[];
  rating: number;
  rating_count: number;
  description: string;
  warnings?: string[];
  allergen_conflict?: boolean;
};

export type NowCastLine = {
  product: Product;
  qty: number;
  reason: string;
  reasons: string[];
  signals: string[];
  line_total: number;
};

export type NowCastGroup = {
  signal: "calendar" | "fridge" | "history";
  title: string;
  icon: string;
  blurb: string;
  subtotal: number;
  items: NowCastLine[];
};

export type CalendarEvent = {
  id: string;
  title: string;
  when_label: string;
  type: string;
  guests?: number;
  is_hero?: boolean;
  summary?: string;
  linked_recipe?: string;
};

export type NowCast = {
  greeting: string;
  headline: string;
  subtext: string;
  event: CalendarEvent | null;
  fridge_sync: string;
  groups: NowCastGroup[];
  item_count: number;
  total: number;
  eta_min: number;
  store: string;
};

export type RecipeSummary = {
  id: string;
  name: string;
  cuisine: string;
  category: string;
  image: string;
  time_min: number;
  dietary_tags: string[];
  ingredient_count: number;
};

export type RecipeIngredient = {
  product: Product | null;
  name: string;
  display_qty: string;
  base_measure: string;
  price: number;
};

export type Recipe = RecipeSummary & {
  base_servings: number;
  servings: number;
  steps: string[];
  ingredients: RecipeIngredient[];
  total: number;
};

export type SpeakResult = {
  reply?: string;
  products: Product[];
  recipe: Recipe | null;
  dietary_note?: string;
  note?: string;
  total: number;
};

export type SosPreset = {
  id: string;
  label: string;
  emoji: string;
  color: string;
  message: string;
  eta_min: number;
  items: Product[];
  total: number;
  item_count: number;
};

export type Bootstrap = {
  settings: {
    store_name: string;
    tagline: string;
    currency: string;
    demo_now_label: string;
    delivery_zone: string;
    dark_store: string;
    eta_default_min: number;
    eta_sos_min: number;
    free_delivery_above: number;
    delivery_fee: number;
  };
  user: {
    id: string;
    name: string;
    first_name: string;
    avatar_color: string;
    address: { label?: string; line1: string; line2: string; city: string; pincode: string };
    payment: { type: string; label: string; masked: string };
    dietary: { preferences: string[]; preferences_label: string; allergens: string[]; note: string };
  };
  categories: { id: string; label: string; emoji: string }[];
};

export type Dietary = {
  preferences: string[];
  preferences_label: string;
  allergens: string[];
  exclude_keywords: string[];
  note?: string;
};

export type Profile = {
  name: string;
  first_name: string;
  age: number;
  avatar_color: string;
  household: string;
  address: { label?: string; line1: string; line2: string; city: string; pincode: string };
  payment: { type: string; label: string; masked: string };
  dietary: Dietary;
  diet_options: string[];
  allergen_options: string[];
};

export type GroupMember = {
  name: string;
  color: string;
  relation: string;
  host: boolean;
  subtotal: number;
  item_count: number;
};

export type GroupItem = {
  product: Product;
  qty: number;
  added_by: string;
  added_by_color: string;
  line_total: number;
};

export type GroupCart = {
  id: string;
  code: string;
  host: string;
  members: GroupMember[];
  items: GroupItem[];
  item_count: number;
  total: number;
};

export type PastOrder = {
  order_id: string;
  date: string;
  status: string;
  items: { product: Product; qty: number }[];
  item_count: number;
  total: number;
};

export type Coupon = {
  code: string;
  title: string;
  type: string;
  value: number;
  min_order: number;
  desc: string;
  category?: string;
  max_discount?: number;
  payment?: string;
  eligible: boolean;
  reason: string;
  discount: number;
};

export type CouponEval = {
  subtotal: number;
  delivery_fee: number;
  best_code: string | null;
  coupons: Coupon[];
};

export type Order = {
  order_id: string;
  items: { product: Product; qty: number; line_total: number }[];
  item_count: number;
  subtotal: number;
  delivery_fee: number;
  discount?: number;
  coupon?: { code: string; title: string; discount: number } | null;
  savings?: number;
  total: number;
  eta_min: number;
  address: { line1: string; line2: string; city: string; pincode: string };
  store: string;
  stages: string[];
};

// ── AI Dish Recognition ────────────────────────────────────────────────────

export type DishIngredient = {
  name: string;
  display_qty: string;
  qty: number;
  unit: string;
  search_term: string;
  product: Product | null;
  price: number;
  available: boolean;
};

export type DishAnalysis = {
  dish_name: string;
  cuisine: string;
  cooking_time_min: number;
  base_servings: number;
  ingredients: DishIngredient[];
  ingredient_count: number;
  /** Hero image URL — set when a stored recipe was matched, undefined for AI-generated results */
  image?: string;
  /** True when the result came from an existing stored recipe */
  from_stored_recipe?: boolean;
  /** Recipe id — present only when from_stored_recipe is true; used to re-fetch on servings change */
  recipe_id?: string;
};

