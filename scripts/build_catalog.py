#!/usr/bin/env python3
"""
Build the Amazon Now product catalog.

- Hero products are hand-authored (Indian brands, INR prices, real detail).
- Images are downloaded LOCAL so the demo never depends on the network at
  record time:
    * food/grocery  -> TheMealDB ingredient thumbnails (clean white-bg shots)
    * non-food      -> first Unsplash candidate URL that returns 200
- Emits config/catalog.json and downloads to frontend/public/products/.

Run:  uv run scripts/build_catalog.py   (from repo root)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "frontend", "public", "products")
CONFIG_DIR = os.path.join(ROOT, "config")
MEALDB = "https://www.themealdb.com/images/ingredients/{}-Medium.png"

os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (AmazonNow demo data builder)"}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.status


def download(url, dest):
    try:
        data, status = fetch(url)
        if status == 200 and len(data) > 1500:  # guard against tiny error blobs
            with open(dest, "wb") as f:
                f.write(data)
            return True
    except Exception:
        return False
    return False


# Reusable Unsplash candidate photos by sub-category (validated stable IDs).
U = lambda pid: f"https://images.unsplash.com/photo-{pid}?w=500&q=80"
NONFOOD = {
    "pills": [U("1584308666744-24d5c474f2ae"), U("1471864190281-a93a3070b6de")],
    "syrup": [U("1550572017-edd951b55104"), U("1471864190281-a93a3070b6de")],
    "thermometer": [U("1584634731339-252c581abfc5")],
    "bandaid": [U("1603398938378-e54eab446dde"), U("1471864190281-a93a3070b6de")],
    "sanitizer": [U("1584483766114-2cea6facdf57"), U("1600857544200-b2f666a9a2ec")],
    "vitamin": [U("1550572017-edd951b55104"), U("1471864190281-a93a3070b6de")],
    "whitewine": [U("1510812431401-41d2bd2722f3")],
    "redwine": [U("1553361371-9b22f78e8b1d")],
    "beer": [U("1608270586620-248524c67de9"), U("1535958636474-b021ee887b13")],
    "detergent": [U("1610557892470-55d9e80c0bce")],
    "dishwash": [U("1585421514738-01798e348b17"), U("1610557892470-55d9e80c0bce")],
    "soap": [U("1600857544200-b2f666a9a2ec")],
    "shampoo": [U("1556228578-8c89e6adf883"), U("1600857544200-b2f666a9a2ec")],
    "tissue": [U("1583947581924-860bda6a26df")],
    "diapers": [U("1515488042361-ee00e0ddd4e4")],
    "formula": [U("1612257999756-94f1e6f5f0f8"), U("1471864190281-a93a3070b6de")],
    "pads": [U("1628771065518-0d82f1938462"), U("1583947581924-860bda6a26df")],
    "facewash": [U("1556228578-8c89e6adf883"), U("1600857544200-b2f666a9a2ec")],
    "flowers": [U("1561181286-d3efa7dcc180")],
    "candle": [U("1603006905003-be475563bc64")],
    "handwash": [U("1600857544200-b2f666a9a2ec")],
    "napkins": [U("1583947581924-860bda6a26df")],
    "cups": [U("1517256064527-09c73fc73e38")],
    "tissues": [U("1584305574647-0cc949a2bb9f")],
    "card": [U("1549465220-1a8b9238cd48")],
    "gift_bag": [U("1549465220-1a8b9238cd48")],
    "perfume": [U("1556228578-8c89e6adf883")],
    "cleaner": [U("1528459801416-a9e53bbf4e17")],
    "ice": [U("1608270586620-248524c67de9")],
    "wipes": [U("1584305574647-0cc949a2bb9f"), U("1515488042361-ee00e0ddd4e4"),U("1584305574647-0cc949a2bb9f")],
    "sunscreen": [U("1556228578-8c89e6adf883")],
    "coconut water": [U("1561668045-21d96075905d")],
    "balloons": [U("1519758245394-bc2396a0cfcc"), U("1590228192057-24bbf703a65f")],
    "vaporub": [U("1618086883601-e88a3d62b7e6")],
}

# Catalog rows. img is either ("m", "<MealDB ingredient>") or ("n", "<NONFOOD key>")
# (id, name, brand, price, size, category, img, diet, allergens, rating, desc)
V, VG, GF = "vegetarian", "vegan", "gluten-free"
PRODUCTS = [
    # ---- dairy_eggs ----
    ("amul-milk-500ml", "Amul Taaza Toned Milk", "Amul", 28, "500 ml", "dairy_eggs", ("m", "Milk"), [V, GF], ["dairy"], 4.5, "Homogenised toned milk, 3% fat."),
    ("amul-gold-1l", "Amul Gold Full Cream Milk", "Amul", 75, "1 L", "dairy_eggs", ("m", "Milk"), [V, GF], ["dairy"], 4.6, "Rich full-cream milk, 6% fat."),
    ("farm-eggs-6", "Farm Fresh Brown Eggs", "Eggoz", 84, "6 pcs", "dairy_eggs", ("m", "Eggs"), [GF], ["eggs"], 4.4, "Cage-free brown eggs, protein-rich."),
    ("farm-eggs-12", "Farm Fresh Eggs", "Eggoz", 99, "12 pcs", "dairy_eggs", ("m", "Eggs"), [GF], ["eggs"], 4.4, "A dozen farm-fresh white eggs."),
    ("amul-butter-100g", "Amul Butter", "Amul", 56, "100 g", "dairy_eggs", ("m", "Butter"), [V, GF], ["dairy"], 4.7, "Utterly butterly delicious salted butter."),
    ("amul-paneer-200g", "Amul Malai Paneer", "Amul", 95, "200 g", "dairy_eggs", ("m", "Paneer"), [V, GF], ["dairy"], 4.5, "Soft fresh cottage cheese."),
    ("nestle-curd-400g", "Dahi / Curd", "Nestle a+", 45, "400 g", "dairy_eggs", ("m", "Yogurt"), [V, GF], ["dairy"], 4.3, "Thick set fresh curd."),
    ("greek-yogurt-100g", "Greek Yogurt", "Epigamia", 60, "90 g", "dairy_eggs", ("m", "Greek Yogurt"), [V, GF], ["dairy"], 4.4, "High-protein creamy Greek yogurt."),
    ("amul-cheese-slices", "Cheese Slices", "Amul", 130, "100 g", "dairy_eggs", ("m", "Cheese"), [V], ["dairy"], 4.4, "Processed cheese slices, 10 pcs."),
    ("mozzarella-200g", "Mozzarella Cheese", "Go", 199, "200 g", "dairy_eggs", ("m", "Mozzarella"), [V], ["dairy"], 4.5, "Stretchy pizza-style mozzarella."),
    ("parmesan-150g", "Parmesan Cheese", "Britannia", 320, "150 g", "dairy_eggs", ("m", "Parmesan"), [V], ["dairy"], 4.6, "Aged hard cheese, grated."),
    ("mascarpone-250g", "Mascarpone Cheese", "Impero", 380, "250 g", "dairy_eggs", ("m", "Mascarpone"), [V], ["dairy"], 4.5, "Italian soft cheese for desserts."),
    ("fresh-cream-200ml", "Fresh Cream", "Amul", 72, "200 ml", "dairy_eggs", ("m", "Double Cream"), [V, GF], ["dairy"], 4.4, "25% fat fresh dairy cream."),
    ("amul-ghee-500ml", "Pure Ghee", "Amul", 320, "500 ml", "dairy_eggs", ("m", "Ghee"), [V, GF], ["dairy"], 4.7, "Clarified butter, rich aroma."),

    # ---- bakery ----
    ("brown-bread", "Whole Wheat Brown Bread", "Britannia", 45, "400 g", "bakery", ("m", "Bread"), [V], ["gluten"], 4.3, "Soft whole-wheat sandwich bread."),
    ("white-bread", "White Sandwich Bread", "Modern", 40, "350 g", "bakery", ("m", "Bread"), [V], ["gluten"], 4.2, "Classic soft white bread."),
    ("pav-buns", "Ladi Pav", "Britannia", 35, "6 pcs", "bakery", ("m", "Bread"), [V], ["gluten"], 4.3, "Soft pav buns for misal & vada pav."),
    ("burger-buns", "Burger Buns", "The Health Factory", 60, "4 pcs", "bakery", ("m", "Bread"), [V], ["gluten", "eggs"], 4.2, "Sesame-topped burger buns."),
    ("croissant", "Butter Croissant", "Theobroma", 90, "2 pcs", "bakery", ("m", "Bread"), [V], ["gluten", "dairy", "eggs"], 4.5, "Flaky all-butter croissants."),

    # ---- fresh_produce ----
    ("onion-1kg", "Onion", "Fresho", 39, "1 kg", "fresh_produce", ("m", "Onion"), [VG, GF], [], 4.1, "Fresh red onions."),
    ("tomato-500g", "Tomato", "Fresho", 25, "500 g", "fresh_produce", ("m", "Tomatoes"), [VG, GF], [], 4.0, "Ripe red tomatoes."),
    ("potato-1kg", "Potato", "Fresho", 32, "1 kg", "fresh_produce", ("m", "Potatoes"), [VG, GF], [], 4.1, "Everyday cooking potatoes."),
    ("garlic-200g", "Garlic", "Fresho", 38, "200 g", "fresh_produce", ("m", "Garlic"), [VG, GF], [], 4.2, "Fresh garlic bulbs."),
    ("ginger-150g", "Ginger", "Fresho", 28, "150 g", "fresh_produce", ("m", "Ginger"), [VG, GF], [], 4.2, "Fresh ginger root."),
    ("spinach", "Palak / Spinach", "Fresho", 22, "250 g", "fresh_produce", ("m", "Spinach"), [VG, GF], [], 4.1, "Tender green spinach."),
    ("capsicum", "Capsicum (Green)", "Fresho", 30, "250 g", "fresh_produce", ("m", "Red Pepper"), [VG, GF], [], 4.0, "Crunchy green bell peppers."),
    ("mushroom-200g", "Button Mushrooms", "Fresho", 49, "200 g", "fresh_produce", ("m", "Mushrooms"), [VG, GF], [], 4.3, "Fresh white button mushrooms."),
    ("lemon-4", "Lemon", "Fresho", 24, "4 pcs", "fresh_produce", ("m", "Lemon"), [VG, GF], [], 4.1, "Juicy lemons."),
    ("banana-6", "Banana (Robusta)", "Fresho", 38, "6 pcs", "fresh_produce", ("m", "Banana"), [VG, GF], [], 4.2, "Ripe sweet bananas."),
    ("apple-4", "Royal Gala Apple", "Fresho", 145, "4 pcs", "fresh_produce", ("m", "Apple"), [VG, GF], [], 4.3, "Crisp imported apples."),
    ("carrot-500g", "Carrot", "Fresho", 35, "500 g", "fresh_produce", ("m", "Carrots"), [VG, GF], [], 4.2, "Sweet orange carrots."),
    ("coriander", "Coriander Leaves", "Fresho", 12, "100 g", "fresh_produce", ("m", "Coriander"), [VG, GF], [], 4.0, "Fresh dhania for garnish."),
    ("green-chilli", "Green Chilli", "Fresho", 15, "100 g", "fresh_produce", ("m", "Chilli"), [VG, GF], [], 4.0, "Spicy green chillies."),
    ("basil", "Fresh Basil", "Fresho", 49, "25 g", "fresh_produce", ("m", "Basil"), [VG, GF], [], 4.2, "Aromatic basil leaves."),

    # ---- staples_grocery ----
    ("basmati-rice-1kg", "India Gate Basmati Rice", "India Gate", 145, "1 kg", "staples_grocery", ("m", "Basmati Rice"), [VG, GF], [], 4.6, "Long-grain aged basmati."),
    ("atta-5kg", "Aashirvaad Atta", "Aashirvaad", 270, "5 kg", "staples_grocery", ("m", "Flour"), [VG], ["gluten"], 4.6, "Whole-wheat chakki atta."),
    ("spaghetti", "Durum Wheat Spaghetti", "Del Monte", 110, "500 g", "staples_grocery", ("m", "Spaghetti"), [VG], ["gluten"], 4.4, "Italian-style spaghetti."),
    ("penne", "Penne Pasta", "Del Monte", 110, "500 g", "staples_grocery", ("m", "Penne Rigate"), [VG], ["gluten"], 4.4, "Ridged penne pasta."),
    ("toor-dal", "Toor Dal", "Tata Sampann", 160, "1 kg", "staples_grocery", ("m", "Red Lentils"), [VG, GF], [], 4.5, "Unpolished split pigeon peas."),
    ("chana-dal", "Chana Dal", "Tata Sampann", 95, "500 g", "staples_grocery", ("m", "Chickpeas"), [VG, GF], [], 4.4, "Split Bengal gram."),
    ("sugar-1kg", "Sugar", "Madhur", 48, "1 kg", "staples_grocery", ("m", "Sugar"), [VG, GF], [], 4.3, "Fine white sugar."),
    ("salt-1kg", "Iodised Salt", "Tata Salt", 28, "1 kg", "staples_grocery", ("m", "Salt"), [VG, GF], [], 4.7, "Vacuum-evaporated iodised salt."),
    ("olive-oil-500ml", "Extra Virgin Olive Oil", "Figaro", 480, "500 ml", "staples_grocery", ("m", "Olive Oil"), [VG, GF], [], 4.5, "Cold-pressed olive oil."),
    ("sunflower-oil-1l", "Sunflower Oil", "Fortune", 140, "1 L", "staples_grocery", ("m", "Vegetable Oil"), [VG, GF], [], 4.3, "Refined sunflower cooking oil."),
    ("maida-1kg", "Maida / Refined Flour", "Aashirvaad", 52, "1 kg", "staples_grocery", ("m", "Plain Flour"), [VG], ["gluten"], 4.2, "Refined wheat flour."),
    ("besan-500g", "Besan / Gram Flour", "Rajdhani", 70, "500 g", "staples_grocery", ("m", "Flour"), [VG, GF], [], 4.3, "Stone-ground gram flour."),
    ("black-pepper-100g", "Black Pepper", "Tata Sampann", 130, "100 g", "staples_grocery", ("m", "Black Pepper"), [VG, GF], [], 4.5, "Whole black peppercorns."),
    ("turmeric-200g", "Turmeric Powder", "Tata Sampann", 60, "200 g", "staples_grocery", ("m", "Turmeric"), [VG, GF], [], 4.5, "Pure haldi powder."),
    ("garam-masala", "Garam Masala", "Everest", 75, "100 g", "staples_grocery", ("m", "Garam Masala"), [VG, GF], [], 4.5, "Aromatic spice blend."),
    ("cumin-seeds", "Cumin / Jeera", "Tata Sampann", 55, "100 g", "staples_grocery", ("m", "Cumin"), [VG, GF], [], 4.4, "Whole cumin seeds."),

    # ---- meat_seafood ----
    ("chicken-breast-500g", "Chicken Breast (Boneless)", "Licious", 230, "500 g", "meat_seafood", ("m", "Chicken Breast"), [GF], [], 4.4, "Antibiotic-free boneless breast."),
    ("chicken-currycut-1kg", "Chicken Curry Cut", "Licious", 285, "1 kg", "meat_seafood", ("m", "Chicken"), [GF], [], 4.4, "Skinless curry-cut with bone."),
    ("mutton-500g", "Mutton Curry Cut", "Licious", 460, "500 g", "meat_seafood", ("m", "Lamb"), [GF], [], 4.3, "Tender goat curry cut."),
    ("prawns-250g", "Prawns (Cleaned)", "Licious", 320, "250 g", "meat_seafood", ("m", "Prawns"), [GF], ["shellfish"], 4.3, "Deveined medium prawns."),
    ("salmon-300g", "Norwegian Salmon", "Licious", 540, "300 g", "meat_seafood", ("m", "Salmon"), [GF], ["fish"], 4.5, "Boneless salmon fillet."),
    ("bacon-200g", "Pork Bacon Rashers", "Prasuma", 290, "200 g", "meat_seafood", ("m", "Bacon"), [GF], [], 4.3, "Smoked streaky bacon."),

    # ---- beverages ----
    ("coffee-beans-250g", "Roasted Coffee Beans", "Blue Tokai", 450, "250 g", "beverages", ("m", "Coffee"), [VG, GF], [], 4.7, "Single-origin medium roast beans."),
    ("instant-coffee-100g", "Instant Coffee", "Nescafe", 320, "100 g", "beverages", ("m", "Coffee"), [VG, GF], [], 4.5, "Rich instant coffee granules."),
    ("tea-500g", "Premium Tea", "Tata Tea Gold", 290, "500 g", "beverages", ("m", "Tea"), [VG, GF], [], 4.5, "Assam blend leaf tea."),
    ("green-tea-25", "Green Tea Bags", "Tetley", 150, "25 bags", "beverages", ("m", "Tea"), [VG, GF], [], 4.3, "Antioxidant-rich green tea."),
    ("orange-juice-1l", "Orange Juice", "Tropicana", 130, "1 L", "beverages", ("m", "Orange"), [VG, GF], [], 4.3, "100% not-from-concentrate juice."),
    ("cola-750ml", "Coca-Cola", "Coca-Cola", 40, "750 ml", "beverages", ("m", "Coca-Cola"), [VG, GF], [], 4.4, "Chilled cola."),
    ("water-1l", "Packaged Drinking Water", "Bisleri", 20, "1 L", "beverages", ("m", "Water"), [VG, GF], [], 4.5, "Mineral water."),
    ("white-wine", "Sauvignon Blanc White Wine", "Sula", 850, "750 ml", "beverages", ("n", "whitewine"), [VG, GF], [], 4.4, "Crisp dry white wine."),
    ("red-wine", "Shiraz Red Wine", "Sula", 920, "750 ml", "beverages", ("n", "redwine"), [VG, GF], [], 4.5, "Bold full-bodied red wine."),
    ("beer-6", "Lager Beer (6-pack)", "Bira 91", 600, "6 x 330 ml", "beverages", ("n", "beer"), [VG, GF], ["gluten"], 4.4, "Crisp white lager."),

    # ---- snacks ----
    ("chips-classic", "Potato Chips (Salted)", "Lay's", 30, "90 g", "snacks", ("m", "Potatoes"), [V, GF], [], 4.3, "Classic salted crisps."),
    ("digestive-biscuits", "Digestive Biscuits", "McVitie's", 80, "250 g", "snacks", ("m", "Digestive Biscuits"), [V], ["gluten"], 4.4, "Wholewheat digestive biscuits."),
    ("namkeen", "Aloo Bhujia", "Haldiram's", 55, "200 g", "snacks", ("m", "Flour"), [V], [], 4.5, "Spicy potato sev namkeen."),
    ("dark-chocolate", "Dark Chocolate 70%", "Amul", 90, "150 g", "snacks", ("m", "Dark Chocolate"), [V, GF], ["dairy"], 4.5, "Intense 70% cocoa chocolate."),
    ("milk-chocolate", "Milk Chocolate", "Cadbury Dairy Milk", 80, "110 g", "snacks", ("m", "Chocolate"), [V], ["dairy"], 4.6, "Creamy milk chocolate."),
    ("popcorn", "Microwave Popcorn", "Act II", 45, "99 g", "snacks", ("m", "Sweetcorn"), [V, GF], [], 4.2, "Butter-flavour popcorn."),
    ("cashews-200g", "Roasted Cashews", "Happilo", 220, "200 g", "snacks", ("m", "Cashew Nuts"), [VG, GF], ["nuts"], 4.5, "Premium roasted & salted cashews."),
    ("almonds-200g", "California Almonds", "Happilo", 240, "200 g", "snacks", ("m", "Almonds"), [VG, GF], ["nuts"], 4.6, "Whole raw almonds."),

    # ---- frozen ----
    ("frozen-peas", "Frozen Green Peas", "Safal", 75, "500 g", "frozen", ("m", "Peas"), [VG, GF], [], 4.3, "Farm-fresh frozen peas."),
    ("french-fries", "Frozen French Fries", "McCain", 110, "420 g", "frozen", ("m", "Potatoes"), [VG], [], 4.3, "Crispy classic fries."),
    ("ice-cream", "Vanilla Ice Cream Tub", "Amul", 180, "1 L", "frozen", ("m", "Ice Cream"), [V, GF], ["dairy"], 4.5, "Rich vanilla ice cream."),
    ("frozen-paratha", "Frozen Malabar Paratha", "ID", 99, "5 pcs", "frozen", ("m", "Flour"), [VG], ["gluten"], 4.3, "Ready-to-cook flaky parathas."),

    # ---- personal_care ----
    ("shampoo", "Anti-Hairfall Shampoo", "Dove", 220, "340 ml", "personal_care", ("n", "shampoo"), [V], [], 4.3, "Nourishing daily shampoo."),
    ("soap-4", "Moisturising Soap (4-pack)", "Dove", 200, "4 x 100 g", "personal_care", ("n", "soap"), [V], [], 4.5, "Cream beauty bar."),
    ("toothpaste", "Cavity-Protection Toothpaste", "Colgate", 95, "150 g", "personal_care", ("n", "facewash"), [V], [], 4.5, "Fluoride toothpaste."),
    ("facewash", "Foaming Face Wash", "Cetaphil", 320, "150 ml", "personal_care", ("n", "facewash"), [V], [], 4.4, "Gentle daily face wash."),
    ("sanitary-pads", "Ultra-Thin Sanitary Pads", "Whisper", 199, "30 pcs", "personal_care", ("n", "pads"), [V], [], 4.5, "Overnight protection pads."),
    ("deodorant", "Body Spray Deodorant", "Nivea", 210, "150 ml", "personal_care", ("n", "soap"), [V], [], 4.3, "Long-lasting freshness."),

    # ---- household_cleaning ----
    ("dishwasher-tabs", "Dishwasher Tablets", "Finish", 540, "60 pcs", "household_cleaning", ("n", "dishwash"), [VG], [], 4.5, "All-in-1 dishwasher tablets."),
    ("dishwash-liquid", "Dishwash Liquid Gel", "Vim", 110, "750 ml", "household_cleaning", ("n", "dishwash"), [VG], [], 4.4, "Lemon dishwash gel."),
    ("detergent", "Matic Liquid Detergent", "Surf Excel", 320, "2 L", "household_cleaning", ("n", "detergent"), [VG], [], 4.5, "Front-load liquid detergent."),
    ("floor-cleaner", "Floor Cleaner Disinfectant", "Lizol", 185, "975 ml", "household_cleaning", ("n", "detergent"), [VG], [], 4.4, "Kills 99.9% germs."),
    ("toilet-cleaner", "Toilet Cleaner", "Harpic", 99, "1 L", "household_cleaning", ("n", "detergent"), [VG], [], 4.4, "Power-plus toilet cleaner."),
    ("garbage-bags", "Garbage Bags (Medium)", "Origami", 160, "90 pcs", "household_cleaning", ("n", "detergent"), [VG], [], 4.3, "Oxo-biodegradable bin bags."),
    ("tissue-box", "Facial Tissues", "Origami", 70, "100 pulls", "household_cleaning", ("n", "tissue"), [VG], [], 4.3, "2-ply soft facial tissues."),

    # ---- medicine_health ----
    ("paracetamol", "Paracetamol 500mg", "Dolo 650", 30, "15 tablets", "medicine_health", ("n", "pills"), [VG, GF], [], 4.7, "Fever & pain relief tablets."),
    ("ors", "ORS Electrolyte (Orange)", "Electral", 22, "21.8 g", "medicine_health", ("n", "vitamin"), [VG, GF], [], 4.6, "Rehydration salts sachet."),
    ("thermometer", "Digital Thermometer", "Dr Trust", 199, "1 unit", "medicine_health", ("n", "thermometer"), [VG, GF], [], 4.4, "Fast-read digital thermometer."),
    ("cough-syrup", "Cough Syrup", "Benadryl", 120, "100 ml", "medicine_health", ("n", "syrup"), [VG, GF], [], 4.3, "Relief for dry cough."),
    ("antacid", "Antacid Liquid (Mint)", "Digene", 95, "200 ml", "medicine_health", ("n", "syrup"), [VG, GF], [], 4.4, "Fast acidity & gas relief."),
    ("bandaid", "Adhesive Bandages", "Band-Aid", 85, "40 pcs", "medicine_health", ("n", "bandaid"), [VG, GF], [], 4.5, "Assorted washproof bandages."),
    ("sanitizer", "Hand Sanitizer", "Dettol", 99, "200 ml", "medicine_health", ("n", "sanitizer"), [VG, GF], [], 4.4, "70% alcohol germ protection."),
    ("vitamin-c", "Vitamin C Effervescent", "Limcee", 110, "20 tablets", "medicine_health", ("n", "vitamin"), [VG, GF], [], 4.4, "Immunity-boosting vitamin C."),

    # ---- baby_care ----
    ("diapers-m", "Baby Diaper Pants (M)", "Pampers", 699, "62 pcs", "baby_care", ("n", "diapers"), [VG], [], 4.6, "12-hr dry pant-style diapers."),
    ("baby-wipes", "Baby Wipes", "Pampers", 199, "72 pcs", "baby_care", ("n", "wipes"), [VG], [], 4.5, "Fragrance-free gentle wipes."),
    ("baby-formula", "Infant Formula Stage 1", "Nan Pro", 750, "400 g", "baby_care", ("n", "formula"), [V], ["dairy"], 4.5, "Spray-dried infant milk formula."),
    ("baby-lotion", "Baby Lotion", "Johnson's", 199, "200 ml", "baby_care", ("n", "soap"), [V], [], 4.5, "Mild moisturising baby lotion."),
# ---- missing food items for the 7 scenarios ----
    ("besan-1kg", "Organic Besan (Gram Flour)", "Rajdhani", 120, "1 kg", "staples_grocery", ("m", "Flour"), [VG, GF], [], 4.5, "Premium fine-ground chana dal flour for frying."),
    ("eno-fruit-salt", "Eno Regular Fruit Salt Sachet", "Eno", 10, "5 g", "medicine_health", ("n", "pills"), [VG, GF], [], 4.8, "Fast-acting relief from acidity and stomach gas."),
    ("raw-coconut-water", "Natural Tender Coconut Water", "Raw Pressery", 70, "200 ml", "beverages", ("m", "Coconut Water"), [VG, GF], [], 4.6, "100% pure naturally hydrating electrolyte beverage."),
    ("pintola-peanut-butter", "Unsweetened Creamy Peanut Butter", "Pintola", 165, "350 g", "snacks", ("m", "Peanut Butter"), [VG, GF], ["nuts"], 4.7, "Pure roasted peanut paste with no added oil or sugars."),
    ("epigamia-almond-milk", "Unsweetened Plant Almond Milk", "Epigamia", 140, "1 L", "dairy_eggs", ("m", "Almond Milk"), [VG, GF], ["nuts"], 4.3, "Creamy plant-based dairy milk alternative."),
    ("ferrero-rocher-4pc", "Ferrero Rocher Premium Chocolates", "Ferrero", 150, "4 pcs", "snacks", ("m", "Chocolate"), [V], ["dairy", "nuts", "gluten"], 4.8, "Crispy hazelnut chocolate truffles."),

    # ---- home_decor_lifestyle ----
    ("red-roses-bouquet", "Fresh Premium Red Roses Bouquet", "Ferns N Petals", 399, "1 bunch", "home_decor_lifestyle", ("n", "flowers"), [VG, GF], [], 4.6, "A bunch of 6 elegant, freshly-cut red roses."),
    ("scented-candle", "Aromatic Lavender Scented Candle", "Miniso", 249, "1 unit", "home_decor_lifestyle", ("n", "candle"), [VG, GF], [], 4.4, "Soothing hand-poured wax jar candle for ambience."),

    # ---- party_festive ----
    ("red-plastic-cups", "Red Party Plastic Cups", "Origami", 85, "25 pcs", "party_festive", ("n", "cups"), [VG, GF], [], 4.2, "Disposable premium red cups for cold beverages."),
    ("soan-papdi-500g", "Premium Soan Papdi Sweet Box", "Haldiram's", 160, "500 g", "party_festive", ("m", "Flour"), [V], ["gluten", "nuts", "dairy"], 4.5, "Flaky traditional sweet made with ghee and dry fruits."),
    ("gift-bag", "Elegant Birthday Gift Bag", "Paperkraft", 60, "1 unit", "party_festive", ("n", "gift_bag"), [VG, GF], [], 4.3, "Thick glossy gift wrapping bag with ribbon handles."),

    # ---- updated extra accessories ----
    ("colin-spray", "Colin Glass and Surface Cleaner", "Colin", 105, "500 ml", "household_cleaning", ("n", "cleaner"), [VG], [], 4.5, "Shine and disinfection booster spray for glass tables."),
    ("hand-sanitizer-wipe", "Dettol Anti-Bacterial Wet Wipes", "Dettol", 75, "15 wipes", "personal_care", ("n", "wipes"), [VG], [], 4.6, "Skin-safe disinfecting travel wet tissues."),

    ("whole-bay-leaf", "Whole Bay Leaf / Tejpatta", "Catch", 45, "20 g", "staples_grocery", ("m", "Bay Leaf"), [VG, GF], [], 4.5, "Aromatically fragrant whole dried bay leaves."),
    ("cinnamon-sticks", "Dalchini / Cinnamon Sticks", "Catch", 65, "50 g", "staples_grocery", ("m", "Cinnamon"), [VG, GF], [], 4.6, "Premium sweet-aroma cinnamon whole sticks."),
    ("whole-cloves", "Laung / Whole Cloves", "Catch", 55, "50 g", "staples_grocery", ("m", "Cloves"), [VG, GF], [], 4.4, "Handpicked premium pungent whole cloves."),
    ("green-cardamom", "Hari Elaichi / Green Cardamom", "Catch", 120, "50 g", "staples_grocery", ("m", "Cardamom"), [VG, GF], [], 4.7, "Whole aromatic green cardamom pods."),
    ("chocolate-cake", "Rich Chocolate Cake Slice", "Bombay Baking", 120, "1 slice", "party_festive", ("n", "candle"), [V], ["gluten", "dairy"], 4.6, "Moist layered chocolate cake with chocolate ganache."),
    ("latex-balloons", "Colourful Latex Balloons", "Party Supplies", 60, "12 pcs", "party_festive", ("n", "balloons"), [VG, GF], [], 4.3, "Assorted bright-coloured 12-inch latex balloons."),
    ("ready-to-eat-soup", "Mixed Vegetable Soup", "Knorr", 50, "65 g", "staples_grocery", ("m", "Soup"), [V, GF], [], 4.2, "Instant cup-of-soup mix, just add hot water."),
    ("vaporub", "Vicks VapoRub", "Vicks", 135, "25 ml", "medicine_health", ("n", "vaporub"), [VG], [], 4.7, "Ayurvedic balm for cold, cough and headache relief."),
    ("honey", "Pure Honey", "Dabur", 195, "500 g", "staples_grocery", ("m", "Honey"), [VG], [], 4.6, "100% pure natural honey for tea and home remedies."),
]


def build():
    catalog = []
    failed = []
    for (pid, name, brand, price, size, cat, img, diet, allergens, rating, desc) in PRODUCTS:
        kind, key = img
        dest = os.path.join(IMG_DIR, f"{pid}.png")
        ok = False
        if os.path.exists(dest) and os.path.getsize(dest) > 1500:
            ok = True
        elif kind == "m":
            ok = download(MEALDB.format(urllib.parse.quote(key)), dest)
        else:  # non-food, try candidates
            for url in NONFOOD.get(key, []):
                if download(url, dest):
                    ok = True
                    break
        if not ok:
            failed.append((pid, kind, key))
        catalog.append({
            "id": pid,
            "name": name,
            "brand": brand,
            "price": price,
            "size": size,
            "category": cat,
            "image": f"/products/{pid}.png" if ok else "",
            "match_key": key.lower() if kind == "m" else "",
            "dietary_tags": diet,
            "allergen_tags": allergens,
            "rating": rating,
            "rating_count": 100 + (abs(hash(pid)) % 4900),
            "description": desc,
        })
        time.sleep(0.05)  # be polite to the source
    with open(os.path.join(CONFIG_DIR, "catalog.json"), "w") as f:
        json.dump({"products": catalog}, f, indent=2, ensure_ascii=False)
    print(f"catalog: {len(catalog)} products, images ok: {len(catalog)-len(failed)}, failed: {len(failed)}")
    for f in failed:
        print("  MISSING:", f)
    return failed


if __name__ == "__main__":
    sys.exit(1 if build() else 0)
