import requests
import time
import random
from typing import Dict, Any, Optional, List
from ingredients import INGREDIENT_DATA

# --- Constants for USDA API ---
USDA_API_KEY = "aaglBWeeh8NzSoSMgEoZuHpZN1PwB6uRey2AwKxc"
USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"
# We will use the search endpoint to find generic foods
USDA_SEARCH_URL = f"{USDA_BASE_URL}/foods/search"

# --- Cost and Allergy Logic ---
DEFAULT_COST_PER_100G = 0.20  # A generic placeholder cost in USD for 100g
# Keywords to automatically assign exclusion tags based on ingredient name
ALLERGY_TAGGING_KEYWORDS = {
    "legume": ["bean", "lentil", "pea", "soy", "chickpea", "mung"],
    "treenut": ["almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut", "macadamia"],
    "peanut": ["peanut"],  # Separate for clarity
    "meat": ["meat", "beef", "pork", "lamb", "veal", "venison", "bison"],
    "poultry": ["chicken", "turkey", "duck", "goose", "quail", "pheasant"],
    "fish": ["fish", "salmon", "tuna", "cod", "halibut", "mackerel", "sardine", "anchovy", "trout", "bass", "snapper"],
    "shellfish": ["shrimp", "prawn", "crab", "lobster", "scallop", "mussel", "oyster", "clam", "squid", "octopus", "crayfish"],
    "dairy": ["milk", "cheese", "butter", "yogurt", "cream", "whey", "casein"],
    "egg": ["egg", "eggs", "mayonnaise", "mayo"],
    "wheat": ["wheat", "flour", "bread", "pasta", "noodle", "cereal"],
    "gluten": ["wheat", "flour", "bread", "pasta", "noodle", "cereal", "barley", "rye", "oats", "malt"]
}

class APIError(Exception):
    """Custom exception for API-related errors."""
    pass

def fetch_with_backoff(url: str, api_key: str, max_retries: int = 5, use_mock: bool = False) -> Dict[str, Any]:
    """
    Fetches data from an API with exponential backoff retry logic.
    Can use either real USDA API or mock data for testing.
    
    Args:
        url: The API endpoint URL
        api_key: The API key for authentication
        max_retries: Maximum number of retry attempts (default: 5)
        use_mock: If True, use mock data instead of real API call
    
    Returns:
        JSON data from the API
        
    Raises:
        APIError: If all retry attempts fail
    """
    for attempt in range(1, max_retries + 1):
        try:
            if use_mock:
                print(f"Mock API call attempt {attempt}/{max_retries}")
                # Use mock USDA API for testing
                mock_response = mock_usda_fetch_data()
                
                # Check if the mock response was successful
                if mock_response.get("success"):
                    print(f"Mock API call successful on attempt {attempt}")
                    return mock_response
                else:
                    # This shouldn't happen with our mock, but handle it
                    raise requests.exceptions.HTTPError("Mock API returned unsuccessful response")
            else:
                print(f"Real API call attempt {attempt}/{max_retries}")
                
                # Make real API call to USDA
                params = {
                    "api_key": api_key,
                    "query": "chicken rice egg potato flour tomato pork loin tuna beef fish salmon",  # Expanded search query for more high-protein/low-cost staples
                    "pageSize": 100,
                    "pageNumber": 1,
                    "dataType": ["Foundation", "SR Legacy"]  # Focus on clean data types
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                # Check if the request was successful
                if response.status_code == 200:
                    print(f"Real API call successful on attempt {attempt}")
                    return response.json()
                else:
                    # Raise an exception for non-200 status codes
                    response.raise_for_status()
                
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            
            print(f"API call failed on attempt {attempt}: {str(e)}")
            
            # If this is the last attempt, raise the error
            if attempt == max_retries:
                raise APIError(f"API call failed after {max_retries} attempts. Last error: {str(e)}")
            
            # Calculate exponential backoff delay: 2^(attempt-1) seconds
            delay = 2 ** (attempt - 1)
            print(f"Waiting {delay} seconds before retry...")
            time.sleep(delay)
    
    # This should never be reached, but just in case
    raise APIError(f"API call failed after {max_retries} attempts")

def fetch_paginated_data(api_key: str) -> Dict[str, Any]:
    """
    Fetches data from USDA API using multiple targeted queries to get up to 500 ingredients.
    
    Args:
        api_key: USDA API key for authentication
    
    Returns:
        Dictionary with success status, data, and message
    """
    # Define 3 targeted queries for faster testing (reduced from 6)
    MEAT_QUERIES = [
        "chicken beef pork turkey",  # Poultry and red meat
        "rice wheat flour oats",     # Grains and starches
        "egg dairy milk cheese"      # Dairy and eggs
    ]
    
    all_ingredients = []
    total_fetched = 0
    
    try:
        for i, query in enumerate(MEAT_QUERIES, 1):
            print(f"Fetching data for query {i}/{len(MEAT_QUERIES)}: '{query}'")
            
            # Use the existing fetch_with_backoff for each query
            search_url = f"{USDA_SEARCH_URL}?api_key={api_key}&query={query}&pageSize=100&pageNumber=1&dataType=Foundation"
            
            api_response = fetch_with_backoff(
                url=search_url,
                api_key=api_key,
                max_retries=3,
                use_mock=False
            )
            
            foods = api_response.get("foods", [])
            if foods:
                # Process and tag each food item
                for food in foods:
                    ingredient = process_and_tag_food_item_simple(food)
                    if ingredient:
                        all_ingredients.append(ingredient)
                        total_fetched += 1
                        
                        # Stop at 150 ingredients for faster testing
                        if total_fetched >= 150:
                            print(f"Reached maximum of 150 ingredients")
                            break
                
                print(f"Query {i} added {len(foods)} foods, total ingredients: {total_fetched}")
            else:
                print(f"Query {i} returned no foods")
            
            # Break if we've reached the limit
            if total_fetched >= 150:
                break
        
        return {
            "success": True,
            "data": all_ingredients,
            "message": f"Successfully fetched and tagged {len(all_ingredients)} ingredients from {len(MEAT_QUERIES)} USDA API queries"
        }
        
    except Exception as e:
        print(f"Error in fetch_paginated_data: {str(e)}")
        raise APIError(f"Failed to fetch paginated data: {str(e)}")

def fetch_and_tag_real_data(query: str, api_key: str) -> Dict[str, Any]:
    """
    Fetches real data from USDA FoodData Central API using paginated approach.
    Now uses fetch_paginated_data for comprehensive ingredient coverage.
    
    Args:
        query: Search query for common foods (now ignored, uses paginated approach)
        api_key: USDA API key for authentication
    
    Returns:
        Dictionary with success status and tagged ingredient data
        
    Raises:
        APIError: If API call fails after retries
    """
    try:
        print(f"Fetching comprehensive data from USDA FoodData Central API using paginated approach")
        
        # Use the new paginated data fetching approach
        return fetch_paginated_data(api_key)
        
    except Exception as e:
        print(f"Error in fetch_and_tag_real_data: {str(e)}")
        raise APIError(f"Failed to fetch and tag real data: {str(e)}")

def process_and_tag_food_item_simple(food: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Process a single food item from USDA API with simplified logic.
    
    Args:
        food: Single food item from USDA API response
    
    Returns:
        Processed ingredient dictionary or None if invalid
    """
    try:
        # Extract basic information
        name = food.get("description", "").strip()
        if not name:
            return None
        
        # Extract nutritional data
        nutrients = food.get("foodNutrients", [])
        protein_g = extract_nutrient_value(nutrients, "Protein")
        fat_g = extract_nutrient_value(nutrients, "Fat")  # Extract fat content
        
        # Apply allergy tagging based on name using simplified keywords
        allergy_tags = assign_allergy_tags_simple(name)
        
        # Estimate cost based on ingredient type and protein content
        cost_per_100g = estimate_ingredient_cost(name, protein_g, 0.0, fat_g)
        
        return {
            "name": name,
            "cost_per_100g": cost_per_100g,
            "protein_g": round(protein_g, 1),
            "carbs_g": 0.0,  # Simplified - not extracting carbs for now
            "fat_g": round(fat_g, 1),  # Now extracting fat content
            "allergy_tags": allergy_tags
        }
        
    except Exception as e:
        print(f"Error processing food item: {str(e)}")
        return None

def assign_allergy_tags_simple(food_name: str) -> List[str]:
    """
    Assign allergy tags based on food name using simplified keyword matching.
    
    Args:
        food_name: Name of the food item
    
    Returns:
        List of allergy tags
    """
    food_lower = food_name.lower()
    tags = []
    
    # Check for each allergen type using simplified keywords
    for allergen, keywords in ALLERGY_TAGGING_KEYWORDS.items():
        if any(keyword in food_lower for keyword in keywords):
            tags.append(allergen)
    
    return tags

def process_and_tag_food_item(food: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Process a single food item from USDA API and apply allergy tagging.
    
    Args:
        food: Single food item from USDA API response
    
    Returns:
        Processed ingredient dictionary or None if invalid
    """
    try:
        # Extract basic information
        name = food.get("description", "").strip()
        if not name:
            return None
        
        # Extract nutritional data
        nutrients = food.get("foodNutrients", [])
        protein_g = extract_nutrient_value(nutrients, "Protein")
        carbs_g = extract_nutrient_value(nutrients, "Carbohydrate, by difference")
        fat_g = extract_nutrient_value(nutrients, "Total lipid (fat)")
        
        # Apply allergy tagging based on name
        allergy_tags = assign_allergy_tags(name)
        
        # Estimate cost (since USDA doesn't provide cost data)
        estimated_cost = estimate_ingredient_cost(name, protein_g, carbs_g, fat_g)
        
        return {
            "name": name,
            "cost_per_100g": round(estimated_cost, 2),
            "protein_g": round(protein_g, 1),
            "carbs_g": round(carbs_g, 1),
            "fat_g": round(fat_g, 1),
            "allergy_tags": allergy_tags
        }
        
    except Exception as e:
        print(f"Error processing food item: {str(e)}")
        return None

def extract_nutrient_value(nutrients: List[Dict[str, Any]], nutrient_name: str) -> float:
    """
    FIXED: Extract nutrient value using name priority, but checking FDC ID 203 
    if name match fails, which is the reliable Protein ID.
    Now also supports Fat extraction with FDC ID 204.
    
    Args:
        nutrients: List of nutrient dictionaries from USDA API
        nutrient_name: Name of the nutrient to extract
    
    Returns:
        Nutrient value in grams, or 0.0 if not found
    """
    
    # 1. Search by Name (primary method) - using correct USDA API structure
    for nutrient in nutrients:
        if nutrient.get("nutrientName") == nutrient_name:
            return float(nutrient.get("value", 0.0))
            
    # 2. Search by FDC ID (secondary, reliable method for Protein, ID 203)
    # This is the FIX for the common USDA JSON name mismatch issue.
    if nutrient_name == "Protein":
        for nutrient in nutrients:
            if nutrient.get("nutrientNumber") == "203": 
                return float(nutrient.get("value", 0.0))
    
    # 3. Search by FDC ID for Fat (Total lipid), ID 204
    if nutrient_name == "Fat" or nutrient_name == "Total lipid":
        for nutrient in nutrients:
            if nutrient.get("nutrientNumber") == "204": 
                return float(nutrient.get("value", 0.0))

    return 0.0

def assign_allergy_tags(food_name: str) -> List[str]:
    """
    Assign allergy tags based on food name analysis.
    
    Args:
        food_name: Name of the food item
    
    Returns:
        List of allergy tags
    """
    food_lower = food_name.lower()
    tags = []
    
    # Define allergen keywords
    allergen_keywords = {
        "legume": ["bean", "beans", "lentil", "lentils", "soy", "soybean", "soybeans", 
                  "pea", "peas", "chickpea", "chickpeas", "garbanzo", "black bean", 
                  "kidney bean", "pinto bean", "navy bean", "lima bean", "edamame"],
        "peanut": ["peanut", "peanuts", "groundnut", "groundnuts"],
        "treenut": ["almond", "almonds", "walnut", "walnuts", "cashew", "cashews", 
                   "pecan", "pecans", "hazelnut", "hazelnuts", "pistachio", "pistachios",
                   "brazil nut", "brazil nuts", "macadamia", "macadamias", "pine nut", "pine nuts"],
        "wheat": ["wheat", "flour", "bread", "pasta", "noodle", "noodles", "cereal"],
        "gluten": ["wheat", "flour", "bread", "pasta", "noodle", "noodles", "cereal", 
                  "barley", "rye", "oats", "malt"],
        "egg": ["egg", "eggs", "egg white", "egg yolk", "mayonnaise", "mayo"],
        "dairy": ["milk", "cheese", "butter", "yogurt", "yoghurt", "cream", "sour cream", 
                 "ice cream", "whey", "casein"],
        "meat": ["meat", "beef", "pork", "lamb", "veal", "venison", "bison"],
        "poultry": ["chicken", "turkey", "duck", "goose", "quail", "pheasant"],
        "fish": ["fish", "salmon", "tuna", "cod", "halibut", "mackerel", "sardine", 
                "anchovy", "trout", "bass", "snapper"],
        "shellfish": ["shrimp", "prawn", "crab", "lobster", "scallop", "mussel", "oyster", 
                     "clam", "squid", "octopus", "crayfish"]
    }
    
    # Check for each allergen type
    for allergen, keywords in allergen_keywords.items():
        if any(keyword in food_lower for keyword in keywords):
            tags.append(allergen)
    
    return tags

def estimate_ingredient_cost(name: str, protein_g: float, carbs_g: float, fat_g: float) -> float:
    """
    Estimate cost per 100g based on ingredient type and nutritional content.
    
    Args:
        name: Ingredient name
        protein_g: Protein content per 100g
        carbs_g: Carbohydrate content per 100g
        fat_g: Fat content per 100g
    
    Returns:
        Estimated cost per 100g in USD
    """
    name_lower = name.lower()
    
    # Base cost estimates by food category
    if any(word in name_lower for word in ["rice", "grain", "cereal", "oats", "quinoa"]):
        return 0.15  # Grains
    elif any(word in name_lower for word in ["chicken", "turkey", "poultry"]):
        return 0.75  # Poultry
    elif any(word in name_lower for word in ["beef", "pork", "lamb", "meat"]):
        return 1.20  # Red meat
    elif any(word in name_lower for word in ["fish", "salmon", "tuna", "cod"]):
        return 1.50  # Fish
    elif any(word in name_lower for word in ["egg", "eggs"]):
        return 0.25  # Eggs
    elif any(word in name_lower for word in ["milk", "cheese", "dairy"]):
        return 0.40  # Dairy
    elif any(word in name_lower for word in ["vegetable", "tomato", "onion", "carrot", "broccoli"]):
        return 0.30  # Vegetables
    elif any(word in name_lower for word in ["fruit", "apple", "banana", "orange", "berry"]):
        return 0.50  # Fruits
    elif any(word in name_lower for word in ["nut", "almond", "walnut", "peanut"]):
        return 2.00  # Nuts
    elif any(word in name_lower for word in ["bean", "lentil", "soy"]):
        return 0.20  # Legumes
    else:
        # Default based on protein content (higher protein = higher cost)
        return 0.10 + (protein_g * 0.02)

def mock_usda_fetch_data() -> Dict[str, Any]:
    """
    Mock USDA API function that simulates real API behavior.
    
    Simulates:
    - 80% success rate (returns INGREDIENT_DATA)
    - 20% failure rate (raises HTTPError with status 503)
    
    Returns:
        Mock ingredient data
        
    Raises:
        requests.exceptions.HTTPError: Simulated API failure
    """
    # Simulate 80% success, 20% failure
    if random.random() < 0.8:
        print("Mock USDA API: Success - returning ingredient data")
        return {
            "success": True,
            "data": INGREDIENT_DATA,
            "message": "Data fetched successfully from mock USDA API"
        }
    else:
        print("Mock USDA API: Simulating service unavailable error")
        # Simulate a 503 Service Unavailable error
        error_response = requests.Response()
        error_response.status_code = 503
        error_response._content = b'{"error": "Service Unavailable"}'
        raise requests.exceptions.HTTPError("503 Server Error: Service Unavailable", response=error_response)
