from pymongo import MongoClient
from bson import ObjectId

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['pet_shop']

# Clear existing products
db.products.delete_many({})

# Sample products data
products = [
    {
        "name": "Premium Dog Food",
        "description": "High-quality nutrition for your dog",
        "price": 2499.00,
        "image": "item12.jpg",
        "category": "Dogs",
        "stock": 50
    },
    {
        "name": "Cat Scratching Post",
        "description": "Durable scratching post with platforms",
        "price": 1659.00,
        "image": "item2.jpg",
        "category": "Accessories",
        "stock": 30
    },
    {
        "name": "Bird Cage",
        "description": "Spacious cage for small to medium birds",
        "price": 3329.00,
        "image": "item3.jpg",
        "category": "Housing",
        "stock": 20
    },
    {
        "name": "Fish Tank Filter",
        "description": "Advanced filtration system for aquariums",
        "price": 24.99,
        "image": "item4.jpg",
        "category": "Equipment"
    },
    {
        "name": "Pet Grooming Kit",
        "description": "Complete grooming set for cats and dogs",
        "price": 2079.00,
        "image": "item5.jpg",
        "category": "Grooming",
        "stock": 40
    },
    {
        "name": "Hamster Wheel",
        "description": "Silent spinning wheel for small pets",
        "price": 14.99,
        "image": "item6.jpg",
        "category": "Toys"
    },
    {
        "name": "Pet Bed",
        "description": "Comfortable and cozy bed for pets",
        "price": 1249.00,
        "image": "item7.jpg",
        "category": "Bedding",
        "stock": 35
    },
    {
        "name": "Cat Toy Set",
        "description": "Interactive toys for cats",
        "price": 19.99,
        "image": "item8.jpg",
        "category": "Toys"
    },
    {
        "name": "Dog Leash",
        "description": "Durable leash for daily walks",
        "price": 15.99,
        "image": "item9.jpg",
        "category": "Accessories"
    },
    {
        "name": "Pet Carrier",
        "description": "Safe and comfortable carrier for travel",
        "price": 2909.00,
        "image": "item10.jpg",
        "category": "Travel",
        "stock": 25
    },
    {
        "name": "Fish Food",
        "description": "Nutritious food for aquarium fish",
        "price": 9.99,
        "image": "item11.jpg",
        "category": "Food"
    },
    {
        "name": "Pet Shampoo",
        "description": "Gentle and effective pet shampoo",
        "price": 12.99,
        "image": "item12.jpg",
        "category": "Grooming"
    }
]

# Insert products into database
result = db.products.insert_many(products)

print(f"Added {len(result.inserted_ids)} products to the database!") 