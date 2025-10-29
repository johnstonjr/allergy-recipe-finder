import itertools
from typing import List, Dict, Any, Optional, Set

# This data is only used as a final fallback if all API fetches fail
INGREDIENT_DATA = [
    {
        "name": "White Rice (Dry)",
        "cost_per_100g": 0.10,
        "protein_g": 7.1,
        "carbs_g": 80.0,
        "fat_g": 0.7,
        "allergy_tags": []
    },
    {
        "name": "Egg (Large, raw, shelled)",
        "cost_per_100g": 0.25,
        "protein_g": 12.6,
        "carbs_g": 1.1,
        "fat_g": 9.5,
        "allergy_tags": ["egg"]
    },
    {
        "name": "Chicken Breast (Raw)",
        "cost_per_100g": 0.75,
        "protein_g": 31.0,
        "carbs_g": 0.0,
        "fat_g": 3.6,
        "allergy_tags": ["poultry", "meat"]
    },
    {
        "name": "All-Purpose Flour",
        "cost_per_100g": 0.15,
        "protein_g": 10.3,
        "carbs_g": 76.3,
        "fat_g": 1.0,
        "allergy_tags": ["wheat", "gluten"]
    },
    {
        "name": "Canned Diced Tomato",
        "cost_per_100g": 0.08,
        "protein_g": 0.9,
        "carbs_g": 3.9,
        "fat_g": 0.2,
        "allergy_tags": []
    }
]

# --- HELPER FUNCTIONS FOR PALATABILITY AND CLEANUP ---
def get_functional_tags(ingredient_name: str) -> Set[str]:
    """Assigns high-level functional tags for diversity checking."""
    name_lower = ingredient_name.lower()
    tags = set()
    
    if any(word in name_lower for word in ["chicken", "turkey", "fish", "pork", "beef", "lamb", "egg", "tofu", "seitan"]):
        tags.add("Protein")
    
    if any(word in name_lower for word in ["rice", "flour", "pasta", "noodle", "bread", "oats", "potato", "quinoa", "starch"]):
        tags.add("Starch")
        
    if any(word in name_lower for word in ["oil", "butter", "cream", "cheese", "fat", "margarine"]):
        tags.add("Fat/Dairy")
        
    if any(word in name_lower for word in ["tomato", "onion", "garlic", "carrot", "pepper", "broccoli", "spinach", "fruit"]):
        tags.add("Produce")

    if not tags:
        tags.add("Other")
        
    return tags

def clean_ingredient_name(name: str) -> str:
    """Strips noisy USDA terms for better readability."""
    replacements = ["raw", "unprepared", "prepared", "unenriched", "cooked", "generic", "canned", "usda", "frozen"]
    
    cleaned_name = name.strip()
    for term in replacements:
        cleaned_name = cleaned_name.replace(f", {term}", "").replace(f" {term}", "").replace(f",{term}", "")

    cleaned_name = cleaned_name[0].upper() + cleaned_name[1:].strip()
    return cleaned_name.split(',')[0].strip()

# --- MAIN SOLVER FUNCTION ---
def find_best_meal(
    data: List[Dict[str, Any]], 
    max_cost: float, 
    min_protein: float, 
    max_fat: float, 
    excluded_tags: List[str], 
    max_ingredients: int = 4
) -> Optional[List[Dict[str, Any]]]:
    """
    Finds the top 5 meal combinations prioritizing DIVERSITY, then PROTEIN, then COST.
    """

    # 1. Safety Filter
    safe_ingredients = []
    for ingredient in data:
        if not any(tag in excluded_tags for tag in ingredient.get("allergy_tags", [])):
            # Attach functional tags for later use
            ingredient['functional_tags'] = get_functional_tags(ingredient['name'])
            safe_ingredients.append(ingredient)

    valid_meals = []

    # 2. Iterate and Combine 
    # FIX: Start the range from 2 to force combinations and diversity.
    for num_ingredients in range(2, max_ingredients + 1): 
        for combo in itertools.combinations(safe_ingredients, num_ingredients):
            
            # --- PALATABILITY & DIVERSITY CHECK ---
            functional_tags_in_combo = set()
            macro_tags_in_combo = set()
            is_duplicate = False
            
            for item in combo:
                # Rule A: Prevent Duplication (Two Starch, Two Protein)
                if 'Starch' in item['functional_tags']:
                    if 'Starch' in macro_tags_in_combo: is_duplicate = True; break
                    macro_tags_in_combo.add('Starch')
                elif 'Protein' in item['functional_tags']:
                    if 'Protein' in macro_tags_in_combo: is_duplicate = True; break
                    macro_tags_in_combo.add('Protein')
                
                functional_tags_in_combo.update(item['functional_tags'])
            
            if is_duplicate: continue

            # Rule B: Enforce Basic Diversity
            diversity_score = len(functional_tags_in_combo)
            if diversity_score < 2:
                 continue

            # --- NUMERICAL CALCULATIONS ---
            total_cost = sum(item["cost_per_100g"] for item in combo)
            total_protein = sum(item["protein_g"] for item in combo)
            total_fat = sum(item["fat_g"] for item in combo) 
            
            # 4. Apply Soft Constraints
            if (total_cost <= max_cost and 
                total_protein >= min_protein and 
                total_fat <= max_fat): 
                
                valid_meals.append({
                    "ingredients": [clean_ingredient_name(item["name"]) for item in combo],
                    "total_cost": round(total_cost, 2),
                    "total_protein_g": round(total_protein, 1),
                    "total_fat_g": round(total_fat, 1), 
                    "num_ingredients": num_ingredients,
                    "diversity_score": diversity_score
                })

    # 5. Optimization/Ranking
    if not valid_meals:
        return None

    # Overhaul Ranking Priority: 1. Diversity (Max), 2. Protein (Max), 3. Cost (Min)
    valid_meals.sort(key=lambda meal: (-meal["diversity_score"], -meal["total_protein_g"], meal["total_cost"]))
    
    # 6. Return the top 5
    return valid_meals[:5]