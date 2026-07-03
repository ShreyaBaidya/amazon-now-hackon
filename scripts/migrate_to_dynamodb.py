import json
from pathlib import Path
import boto3
import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
AWS_REGION = os.environ.get("AWS_REGION") # Use environment variable or default
USERS_TABLE_NAME = os.environ.get("USERS_TABLE_NAME", "user_profiles")
PRODUCTS_TABLE_NAME = os.environ.get("PRODUCTS_TABLE_NAME", "products")
print("AWS_REGION =", AWS_REGION)
print("USERS_TABLE_NAME =", USERS_TABLE_NAME)
print("PRODUCTS_TABLE_NAME =", PRODUCTS_TABLE_NAME)

# --- Initialize DynamoDB client ---
try:
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    users_table = dynamodb.Table(USERS_TABLE_NAME)
    products_table = dynamodb.Table(PRODUCTS_TABLE_NAME)
except Exception as e:
    print(f"Error initializing DynamoDB clients. Ensure AWS_REGION is set correctly and credentials are valid. Error: {e}")
    exit(1) # Exit if clients cannot be initialized

def _convert_to_decimal(data):
    """Recursively converts float values in data to Decimal for DynamoDB compatibility."""
    if isinstance(data, dict):
        return {k: _convert_to_decimal(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_convert_to_decimal(item) for item in data]
    elif isinstance(data, float):
        return Decimal(str(data)) # Convert float to Decimal
    else:
        return data

def migrate_users():
    print(f"Migrating users to {USERS_TABLE_NAME}...")
    try:
        with open(CONFIG_DIR / "personas.json", "r", encoding="utf-8") as f:
            personas_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: personas.json not found at {CONFIG_DIR / 'personas.json'}")
        return

    for user in personas_data.get("users", []):
        try:
            # DynamoDB expects Decimal for numbers like price, rating etc.
            # We'll assume user data doesn't have floats that need conversion for now, but if it does, _convert_to_decimal would be needed.
            users_table.put_item(Item=user)
            print(f"  Added user: {user.get('id')}")
        except Exception as e:
            print(f"  Error adding user {user.get('id')}: {e}")
    print("User migration complete.")

def migrate_products():
    print(f"Migrating products to {PRODUCTS_TABLE_NAME}...")
    try:
        with open(CONFIG_DIR / "catalog.json", "r", encoding="utf-8") as f:
            catalog_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: catalog.json not found at {CONFIG_DIR / 'catalog.json'}")
        return

    for product in catalog_data.get("products", []):
        try:
            # Convert float types to Decimal for DynamoDB compatibility
            product_decimal = _convert_to_decimal(product)
            products_table.put_item(Item=product_decimal)
            print(f"  Added product: {product.get('id')}")
        except Exception as e:
            print(f"  Error adding product {product.get('id')}: {e}")
    print("Product migration complete.")

if __name__ == "__main__":
    # Ensure AWS_REGION is set as an environment variable before running this script.
    if not AWS_REGION or AWS_REGION == "us-east-1": # Check if it's unset or using default if not intended
        print("Warning: AWS_REGION might not be set correctly. Please ensure it's set to your actual AWS region (e.g., 'ap-south-1').")
        # You could exit here if AWS_REGION is critical and unset, but we'll let boto3 error out

    migrate_users()
    migrate_products()
    print("\nMigration script finished.")
