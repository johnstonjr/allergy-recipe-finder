import requests
import json
import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
# Import the recipe utilities
from recipe_utils import search_recipes_by_ingredient, get_recipe_details, RecipeAPIError
# Keep api_utils for potential future nutrient lookups, but not primary use
from api_utils import APIError, USDA_API_KEY # Assuming api_utils still exists, though not used directly here
from typing import List, Dict, Any
import time

app = Flask(__name__)
CORS(app)

# --- LLM API Configuration ---
LLM_API_KEY = "AIzaSyCjdJ8NVp3p6vqN60_B4OJC6jHxPRign_w" # Your Gemini API Key
LLM_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

# --- Allergy Keywords Mapping (Keep as is) ---
ALLERGY_KEYWORD_MAP = {
    "legume": ["bean", "beans", "lentil", "lentils", "pea", "peas", "chickpea", "chickpeas",
               "garbanzo", "soy", "soybean", "edamame", "black bean", "kidney bean",
               "pinto bean", "navy bean", "lima bean", "mung bean"],
    "legumes": ["bean", "beans", "lentil", "lentils", "pea", "peas", "chickpea", "chickpeas",
                "garbanzo", "soy", "soybean", "edamame", "black bean", "kidney bean",
                "pinto bean", "navy bean", "lima bean", "mung bean"],
    "peanut": ["peanut", "peanuts", "groundnut"],
    "peanuts": ["peanut", "peanuts", "groundnut"],
    "treenut": ["almond", "almonds", "walnut", "walnuts", "cashew", "cashews", "pecan", "pecans",
                "hazelnut", "hazelnuts", "pistachio", "pistachios", "brazil nut", "macadamia"],
    "treenuts": ["almond", "almonds", "walnut", "walnuts", "cashew", "cashews", "pecan", "pecans",
                 "hazelnut", "hazelnuts", "pistachio", "pistachios", "brazil nut", "macadamia"],
    "egg": ["egg", "eggs", "mayonnaise", "mayo", "egg white", "egg yolk"],
    "eggs": ["egg", "eggs", "mayonnaise", "mayo", "egg white", "egg yolk"],
    "dairy": ["milk", "cheese", "butter", "yogurt", "cream", "whey", "casein"],
    "wheat": ["wheat", "flour", "bread", "pasta", "noodle", "noodles", "cereal"],
    "gluten": ["wheat", "flour", "bread", "pasta", "noodle", "noodles", "cereal", "barley", "rye", "oats"]
}

# --- Re-introduced LLM Function ---
def generate_enhanced_recipe(recipe_details: Dict[str, Any]) -> Dict[str, Any]:
    """Uses the Gemini API to enhance instructions from TheMealDB."""
    original_title = recipe_details['title']
    ingredients_list = ", ".join(recipe_details['ingredients'])
    original_instructions = "\n".join(recipe_details['instructions'])

    system_prompt = (
        "You are a helpful cooking assistant focused on safety, clarity, and budget-friendliness for allergy sufferers. "
        "Rewrite the provided recipe instructions to be simpler (3-5 clear steps), explicitly mention cooking temperatures/doneness for any meat/fish (e.g., 165°F for chicken), and maintain a low-cost tone. "
        "Use ONLY the ingredients listed. Do not add or suggest others. "
        "Return the original title and the enhanced instructions in JSON format."
    )

    user_query = (
        f"Enhance the following recipe:\n"
        f"Title: {original_title}\n"
        f"Ingredients: {ingredients_list}\n"
        f"Original Instructions:\n{original_instructions}\n\n"
        f"Provide the rewritten instructions focusing on simplicity, safety (cooking temps!), and using only the listed ingredients."
    )

    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "object",
                "properties": {
                    "enhanced_instructions": {
                        "type": "array",
                        "items": {"type": "string", "description": "One clear, enhanced cooking step."}
                    }
                },
                "required": ["enhanced_instructions"]
            }
        },
        "systemInstruction": {"parts": [{"text": system_prompt}]}
    }

    max_retries = 3
    for attempt in range(max_retries):
        # DEBUG: Print ingredients and instructions being sent
        print(f"--- LLM Enhancement Attempt {attempt + 1} for '{original_title}' ---")
        print(f"[DEBUG] Ingredients List: {ingredients_list}")
        print(f"[DEBUG] Original Instructions:\n{original_instructions}")
        
        try:
            # DEBUG: Print the full payload being sent
            payload_json = json.dumps(payload, indent=2)
            print(f"[DEBUG] Full Payload Being Sent:\n{payload_json}")
            
            response = requests.post(
                LLM_API_URL,
                headers={
                    'Content-Type': 'application/json',
                    'X-Goog-Api-Key': LLM_API_KEY # Key sent in header
                },
                data=json.dumps(payload),
                timeout=25 # Increased timeout slightly
            )
            
            # DEBUG: Print response status and raw text
            print(f"[DEBUG] Response Status Code: {response.status_code}")
            print(f"[DEBUG] Response Text (Raw):\n{response.text}")
            
            response.raise_for_status()

            result = response.json()
            json_text = result['candidates'][0]['content']['parts'][0]['text']
            recipe_data = json.loads(json_text)

            # Return original title + enhanced instructions
            return {
                "title": original_title,
                "instructions": recipe_data.get("enhanced_instructions", recipe_details['instructions']) # Fallback to original
            }
        except Exception as e:
            error_details = ""
            resp = locals().get('response')
            if resp is not None and resp.status_code in [401, 403, 429]: # Check for auth or rate limit errors
                error_details = f" (Status: {resp.status_code})"
            print(f"LLM Enhancer failed on attempt {attempt + 1}: {e}{error_details}")
            if attempt < max_retries - 1:
                delay = 2 ** attempt
                time.sleep(delay)
            else:
                print(f"LLM Enhancer failed all retries for '{original_title}'. Using original instructions.")
                # Fallback: Return the original details if LLM fails
                return {
                    "title": original_title,
                    "instructions": recipe_details['instructions']
                }
    # Should not be reached, but included for safety
    return { "title": original_title, "instructions": recipe_details['instructions']}


# --- Helper Functions: Allergy & Dietary Checks (Unchanged) ---
def check_recipe_allergens(recipe_ingredients: List[str], excluded_tags: List[str]) -> bool:
    if not excluded_tags: return True
    keywords_to_check = set()
    for tag in excluded_tags:
        tag_lower = tag.lower()
        keywords_to_check.update(ALLERGY_KEYWORD_MAP.get(tag_lower, {tag_lower}))
    for ingredient_line in recipe_ingredients:
        ingredient_lower = ingredient_line.lower()
        for keyword in keywords_to_check:
            if keyword in ingredient_lower:
                print(f"Allergy found: '{ingredient_line}' contains '{keyword}'. Discarding.")
                return False
    return True

def check_recipe_dietary(recipe_title: str, recipe_ingredients: List[str], preference: str) -> bool:
    if preference == 'none': return True
    meat_poultry_tags = ['meat', 'poultry', 'beef', 'pork', 'sausage', 'chicken', 'turkey', 'lamb', 'duck', 'goose', 'venison', 'bison']
    fish_shellfish_tags = ['fish', 'shellfish', 'salmon', 'tuna', 'cod', 'haddock', 'mackerel', 'sardine', 'anchovy', 'trout', 'bass', 'snapper', 'halibut', 'tilapia', 'sea bass', 'shrimp', 'prawn', 'crab', 'lobster', 'scallop', 'mussel', 'oyster', 'clam', 'squid', 'octopus', 'crayfish', 'caviar']
    all_ingredients_lower = " ".join(recipe_ingredients).lower()
    title_lower = recipe_title.lower()
    if preference == 'vegetarian':
        if any(tag in all_ingredients_lower or tag in title_lower for tag in meat_poultry_tags + fish_shellfish_tags):
            print(f"Dietary conflict (Vegetarian): '{recipe_title}' contains meat/fish. Discarding.")
            return False
    elif preference == 'pescetarian':
        if any(tag in all_ingredients_lower or tag in title_lower for tag in meat_poultry_tags):
            print(f"Dietary conflict (Pescetarian): '{recipe_title}' contains meat/poultry. Discarding.")
            return False
    return True


# --- Main Route ---
@app.route('/meal/suggest', methods=['POST'])
def suggest_recipe():
    """Finds recipes via TheMealDB, filters them, and enhances instructions via LLM."""

    # 1. Extract Input (Unchanged)
    try:
        data = request.get_json()
        if not data: return jsonify({"success": False, "message": "No JSON data provided"}), 400
        additional_allergies = data.get('additional_allergies', '')
        available_ingredients_str = data.get('available_ingredients', '')
        dietary_preference = data.get('dietary_preference', 'none').lower()
        user_allergies = [a.strip().lower() for a in additional_allergies.split(',') if a.strip()]
        excluded_tags = user_allergies
    except Exception as e:
        return jsonify({"success": False, "message": f"Invalid input format: {str(e)}"}), 400

    # 2. Recipe Search
    try:
        potential_recipes = []
        if available_ingredients_str:
            first_ingredient = available_ingredients_str.split(',')[0].strip()
            if first_ingredient:
                 potential_recipes = search_recipes_by_ingredient(first_ingredient)
        else:
             potential_recipes = search_recipes_by_ingredient("chicken") # Default search

        if not potential_recipes:
            return jsonify({"success": False, "message": "No recipes found for your main ingredient."}), 200

        # 3. Filter & Enhance Recipes
        safe_and_enhanced_recipes = []
        for recipe_summary in potential_recipes:
            meal_id = recipe_summary.get('idMeal')
            if not meal_id: continue

            details = get_recipe_details(meal_id)
            if not details: continue

            # Filter by Allergy & Diet
            if not check_recipe_allergens(details['ingredients'], excluded_tags): continue
            if not check_recipe_dietary(details['title'], details['ingredients'], dietary_preference): continue

            # Enhance using LLM
            enhanced_recipe = generate_enhanced_recipe(details) # Call the LLM

            # Add enhanced details to the list
            safe_and_enhanced_recipes.append({
                'title': enhanced_recipe['title'], # Use original title
                'ingredients': details['ingredients'], # Keep original ingredients list
                'instructions': enhanced_recipe['instructions'], # Use ENHANCED instructions
                'thumbnail': details['thumbnail']
            })

            if len(safe_and_enhanced_recipes) >= 5: break # Limit to top 5

        # 4. Return Results
        if safe_and_enhanced_recipes:
            return jsonify({
                "success": True,
                "recipes": safe_and_enhanced_recipes,
                "parameters": { "excluded_tags": excluded_tags, "dietary_preference": dietary_preference },
                "api_info": { "source": "TheMealDB + Gemini LLM", "recipes_found": len(safe_and_enhanced_recipes) }
            })
        else:
            return jsonify({
                "success": False,
                "message": "Found recipes, but none matched your allergy/diet filters.",
                "parameters": {"excluded_tags": excluded_tags, "dietary_preference": dietary_preference}
            }), 200

    except RecipeAPIError as e:
        return jsonify({"success": False, "message": f"Recipe API error: {str(e)}"}), 503
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({"success": False, "error": str(e), "message": "An unexpected error occurred."}), 500

# --- LLM Test Endpoint ---
@app.route('/llm/test', methods=['GET'])
def llm_test_route():
    """Isolated test route to verify the LLM recipe enhancement functionality."""
    mock_recipe = {
        "title": "Chicken Fried Rice",
        "ingredients": ["2 cups cooked rice", "1 chicken breast", "2 eggs", "1 tbsp soy sauce"],
        "instructions": [
            "Cook the rice according to package directions.",
            "Cut the chicken into small pieces and cook in a pan.",
            "Scramble the eggs in the same pan.",
            "Add the rice and soy sauce, mix well.",
            "Serve hot."
        ]
    }
    
    print("\n=== Running ISOLATED LLM TEST ===")
    enhanced_result = generate_enhanced_recipe(mock_recipe)
    print("=== LLM TEST COMPLETE ===\n")
    
    return jsonify({
        "success": True,
        "original_recipe": mock_recipe,
        "enhanced_recipe": enhanced_result,
        "message": "Isolated LLM test complete. Check enhanced_recipe for output quality."
    })

# --- Health Check (Unchanged) ---
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "Allergy Recipe Creator API"})

# Route to serve the index.html file
@app.route('/')
def index():
    # Assumes index.html is in the same directory as app.py
    # For Render, files are typically in '/opt/render/project/src/'
    # Let's try to serve directly first. If issues, might need 'static_folder'
    try:
        # Render places the project root typically one level up from src when running
        # Let's serve from the directory containing app.py
        return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')
    except FileNotFoundError:
         # Fallback if structure is different
         try:
             # Check current working directory
             return send_from_directory(os.getcwd(), 'index.html')
         except FileNotFoundError:
            return "Error: index.html not found. Check server configuration.", 404

# Optional: Route to serve potential future static files (CSS, JS) if you add them
# @app.route('/static/<path:path>')
# def send_static(path):
#     return send_from_directory('static', path)

# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Allergy Recipe Creator API (Recipe-Centric + LLM Enhancement)...")
    app.run(debug=True, host='0.0.0.0', port=5000)