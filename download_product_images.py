import requests
import os
from urllib.parse import urlparse

def download_image(url, filename):
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, 'wb') as f:
            f.write(response.content)
        print(f"Downloaded {filename}")
    else:
        print(f"Failed to download {filename}")

# Create directories if they don't exist
os.makedirs('static/images/products', exist_ok=True)

# Product Images - Dogs
dog_products = [
    ('https://images.unsplash.com/photo-1600369671236-e74521d4b6ad?w=500&h=500&fit=crop', 'dog-food-1.jpg'),
    ('https://images.unsplash.com/photo-1601758174114-e711c0cbaa69?w=500&h=500&fit=crop', 'dog-food-2.jpg'),
    ('https://images.unsplash.com/photo-1576578985983-7278f302ad6d?w=500&h=500&fit=crop', 'dog-toy-1.jpg'),
    ('https://images.unsplash.com/photo-1577734235269-41e1e3399462?w=500&h=500&fit=crop', 'dog-toy-2.jpg'),
    ('https://images.unsplash.com/photo-1599839575945-a9e5af0c3fa5?w=500&h=500&fit=crop', 'dog-bed-1.jpg'),
    ('https://images.unsplash.com/photo-1541599540903-216a46ca1dc0?w=500&h=500&fit=crop', 'dog-collar-1.jpg')
]

# Product Images - Cats
cat_products = [
    ('https://images.unsplash.com/photo-1589924691995-400dc9ecc119?w=500&h=500&fit=crop', 'cat-food-1.jpg'),
    ('https://images.unsplash.com/photo-1600628421055-4d30de868b8f?w=500&h=500&fit=crop', 'cat-food-2.jpg'),
    ('https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=500&h=500&fit=crop', 'cat-toy-1.jpg'),
    ('https://images.unsplash.com/photo-1526336024174-e58f5cdd8e13?w=500&h=500&fit=crop', 'cat-bed-1.jpg'),
    ('https://images.unsplash.com/photo-1545249390-6bdfa286564f?w=500&h=500&fit=crop', 'cat-scratch-post.jpg'),
    ('https://images.unsplash.com/photo-1592194996308-7b43878e84a6?w=500&h=500&fit=crop', 'cat-litter-box.jpg')
]

# Product Images - Birds
bird_products = [
    ('https://images.unsplash.com/photo-1606567595334-d39972c85dbe?w=500&h=500&fit=crop', 'bird-food-1.jpg'),
    ('https://images.unsplash.com/photo-1592375601764-5dd6be536f78?w=500&h=500&fit=crop', 'bird-cage-1.jpg'),
    ('https://images.unsplash.com/photo-1591198936750-16d8e15edb9e?w=500&h=500&fit=crop', 'bird-toy-1.jpg'),
    ('https://images.unsplash.com/photo-1595613741160-48501f1492b5?w=500&h=500&fit=crop', 'bird-perch-1.jpg')
]

# Download all product images
for category in [dog_products, cat_products, bird_products]:
    for url, filename in category:
        download_image(url, os.path.join('static/images/products', filename))

print("All product images downloaded successfully!") 