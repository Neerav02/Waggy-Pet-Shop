from pymongo import MongoClient
import shutil
import os

# Local MongoDB connection
local_client = MongoClient('mongodb://localhost:27017/')
local_db = local_client['Petshop']

# Atlas MongoDB connection
atlas_client = MongoClient('mongodb+srv://waggy:waggy123@mycluster.o38yu.mongodb.net/Petshop?retryWrites=true&w=majority')
atlas_db = atlas_client['Petshop']

def migrate_products():
    # Create images directory if it doesn't exist
    os.makedirs('static/images', exist_ok=True)
    
    # Get all products from local database
    local_products = list(local_db.products.find())
    
    # Migrate each product
    for product in local_products:
        # Check if image exists and copy it
        if 'image' in product and product['image']:
            src_path = f"static/images/{product['image']}"
            if os.path.exists(src_path):
                # Copy image file
                shutil.copy2(src_path, src_path + '.backup')
            elif not product['image'].startswith('placeholder'):
                # If image doesn't exist, set to placeholder
                product['image'] = 'placeholder.jpg'
        else:
            product['image'] = 'placeholder.jpg'
        
        # Insert product into Atlas
        atlas_db.products.insert_one(product)

    print(f"Migrated {len(local_products)} products")

if __name__ == "__main__":
    try:
        # Clear existing products in Atlas
        atlas_db.products.delete_many({})
        print("Starting product migration...")
        migrate_products()
        print("Product migration completed successfully!")
    except Exception as e:
        print(f"Error during migration: {str(e)}") 