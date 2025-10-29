import requests
from typing import List, Dict, Any, Optional

# Base URL for TheMealDB API (v1, free tier)
THEMEALDB_BASE_URL = "https://www.themealdb.com/api/json/v1/1/"

class RecipeAPIError(Exception):
    """Custom exception for Recipe API issues."""
    pass

def search_recipes_by_ingredient(ingredient: str) -> List[Dict[str, Any]]:
    """
    Searches TheMealDB for recipes containing a primary ingredient.
    Returns a list of basic recipe info (ID, Title, Thumbnail).
    """
    search_url = f"{THEMEALDB_BASE_URL}filter.php"
    params = {'i': ingredient.strip().lower()} # Filter by ingredient
    
    try:
        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        # TheMealDB returns 'meals: null' if no results
        meals = data.get('meals')
        if not meals:
            print(f"No recipes found for ingredient: {ingredient}")
            return []
            
        # Limit results for initial testing (e.g., first 10)
        return meals[:10] 
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching recipes for ingredient '{ingredient}': {e}")
        raise RecipeAPIError(f"Failed to connect to TheMealDB API: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during recipe search: {e}")
        raise RecipeAPIError(f"Unexpected error: {e}")

def get_recipe_details(meal_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches the full details for a single recipe by its ID from TheMealDB.
    Extracts title, instructions, and a clean list of ingredients.
    """
    lookup_url = f"{THEMEALDB_BASE_URL}lookup.php"
    params = {'i': meal_id}
    
    try:
        response = requests.get(lookup_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        meal_details = data.get('meals')
        if not meal_details:
            return None # No details found for this ID
            
        meal = meal_details[0] # API returns a list with one item
        
        # Extract ingredients - TheMealDB stores them in strIngredient1..20 fields
        ingredients = []
        for i in range(1, 21):
            ingredient_key = f'strIngredient{i}'
            measure_key = f'strMeasure{i}'
            
            ingredient = meal.get(ingredient_key)
            measure = meal.get(measure_key)
            
            # Stop if ingredient is null, empty, or whitespace
            if not ingredient or not ingredient.strip():
                break
                
            # Combine measure and ingredient (e.g., "1 cup Flour")
            ingredients.append(f"{measure.strip()} {ingredient.strip()}")
            
        return {
            'id': meal.get('idMeal'),
            'title': meal.get('strMeal'),
            'instructions': meal.get('strInstructions', '').split('\r\n'), # Split instructions into steps
            'ingredients': ingredients, # The cleaned list
            'thumbnail': meal.get('strMealThumb')
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching details for meal ID '{meal_id}': {e}")
        # Don't raise, just return None so the main app can handle it
        return None
    except Exception as e:
        print(f"An unexpected error occurred fetching recipe details: {e}")
        return None

# --- Basic Test Block ---
if __name__ == "__main__":
    print("--- Testing TheMealDB Recipe Search ---")
    test_ingredient = "chicken"
    try:
        recipes = search_recipes_by_ingredient(test_ingredient)
        if recipes:
            print(f"Found {len(recipes)} recipes containing '{test_ingredient}'. First few:")
            for i, recipe in enumerate(recipes[:3]):
                print(f"  {i+1}. ID: {recipe.get('idMeal')}, Title: {recipe.get('strMeal')}")
            
            # Test getting details for the first recipe found
            first_recipe_id = recipes[0].get('idMeal')
            if first_recipe_id:
                print(f"\n--- Testing Recipe Details for ID: {first_recipe_id} ---")
                details = get_recipe_details(first_recipe_id)
                if details:
                    print(f"Title: {details['title']}")
                    print("Ingredients:")
                    for ing in details['ingredients']:
                        print(f"  - {ing}")
                    print("First instruction:", details['instructions'][0] if details['instructions'] else "None")
                else:
                    print("Failed to fetch details.")
        else:
            print("No recipes found in basic search test.")
            
    except RecipeAPIError as e:
        print(f"API Error during test: {e}")