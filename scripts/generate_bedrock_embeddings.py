import os
import json
import boto3
from pinecone import Pinecone, ServerlessSpec
import time
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
PRODUCTS_TABLE_NAME = os.environ.get("PRODUCTS_TABLE_NAME", "products")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.environ.get("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME")

# Titan Embeddings G1 - Text dimensions
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"

# --- Initialize Clients ---
# DynamoDB
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
products_table = dynamodb.Table(PRODUCTS_TABLE_NAME)

# Bedrock runtime client for embeddings
bedrock_runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION)

# Pinecone
if PINECONE_API_KEY and PINECONE_ENVIRONMENT:
    pc = Pinecone(api_key=PINECONE_API_KEY)
else:
    raise ValueError("PINECONE_API_KEY and PINECONE_ENVIRONMENT environment variables must be set.")

def get_embedding(text: str) -> list[float]:
    """Generates an embedding for the given text using AWS Bedrock Titan Embeddings."""
    # Bedrock requires a JSON payload
    body = json.dumps({"inputText": text})
    
    response = bedrock_runtime.invoke_model(
        body=body,
        modelId=EMBEDDING_MODEL_ID,
        accept="application/json",
        contentType="application/json"
    )
    
    response_body = json.loads(response.get("body").read())
    return response_body["embedding"]

def create_pinecone_index_if_not_exists():
    indexes = [idx["name"] for idx in pc.list_indexes()]

    if PINECONE_INDEX_NAME not in indexes:
        print(f"Creating Pinecone index '{PINECONE_INDEX_NAME}'...")

        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region=PINECONE_ENVIRONMENT
            )
        )

        while not pc.describe_index(PINECONE_INDEX_NAME).status["ready"]:
            time.sleep(2)

        print("Index ready.")

    else:
        print("Index already exists.")

def generate_and_upload_embeddings():
    print("Starting embedding generation and upload...")
    
    # Ensure index exists
    create_pinecone_index_if_not_exists()
    index = pc.Index(PINECONE_INDEX_NAME)

    # Fetch all products from DynamoDB
    response = products_table.scan()
    all_products = response.get("Items", [])
    print(f"Fetched {len(all_products)} products from DynamoDB.")

    # Batch processing for efficiency
    batch_size = 100 # Adjust based on Bedrock rate limits
    vectors_to_upsert = []

    for i, product in enumerate(all_products):
        # Construct text for embedding
        # You can make this more sophisticated by combining description, brand, categories, etc.
        text_to_embed = f"{product.get('name', '')} {product.get('brand', '')} {product.get('description', '')}"
        if product.get("dietary_tags"): text_to_embed += f" {' '.join(product['dietary_tags'])}"
        if product.get("allergen_tags"): text_to_embed += f" {' '.join(product['allergen_tags'])}"

        try:
            embedding = get_embedding(text_to_embed)
            vectors_to_upsert.append({"id": product["id"], "values": embedding, "metadata": {"name": product["name"], "category": product["category"]}})

            if (i + 1) % batch_size == 0 or (i + 1) == len(all_products):
                print(f"Upserting batch {len(vectors_to_upsert)} products...")
                index.upsert(vectors=vectors_to_upsert)
                vectors_to_upsert = []
                time.sleep(1) # Pause to respect rate limits if needed

        except Exception as e:
            print(f"Error generating/uploading embedding for product {product.get('id')}: {e}")

    print("Embedding generation and upload complete.")

if __name__ == "__main__":
    generate_and_upload_embeddings()
