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
os.makedirs('static/images/slider', exist_ok=True)

# Slider Images
slider_images = [
    ('https://images.unsplash.com/photo-1450778869180-41d0601e046e?w=1600&h=900&fit=crop', 'slider1.jpg'),  # Pet group
    ('https://images.unsplash.com/photo-1601758228041-f3b2795255f1?w=1600&h=900&fit=crop', 'slider2.jpg'),  # Pet products
    ('https://images.unsplash.com/photo-1583337130417-3346a1be7dee?w=1600&h=900&fit=crop', 'slider3.jpg')   # Pet store
]

# Category Images
category_images = [
    ('https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=800&h=600&fit=crop', 'category-dogs.jpg'),
    ('https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=800&h=600&fit=crop', 'category-cats.jpg'),
    ('https://images.unsplash.com/photo-1552728089-57bdde30beb3?w=800&h=600&fit=crop', 'category-birds.jpg')
]

# Download slider images
for url, filename in slider_images:
    download_image(url, os.path.join('static/images/slider', filename))

# Download category images
for url, filename in category_images:
    download_image(url, os.path.join('static/images', filename))

print("All images downloaded successfully!") 