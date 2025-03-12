from PIL import Image, ImageDraw
import os

def create_placeholder_image():
    # Create images directory if it doesn't exist
    os.makedirs('static/images', exist_ok=True)
    
    # Create a placeholder image
    width = 400
    height = 400
    background_color = (240, 240, 240)
    
    # Create new image with white background
    image = Image.new('RGB', (width, height), background_color)
    draw = ImageDraw.Draw(image)
    
    # Draw a border
    border_color = (200, 200, 200)
    border_width = 2
    draw.rectangle([(0, 0), (width-1, height-1)], outline=border_color, width=border_width)
    
    # Draw a camera icon (simplified)
    camera_color = (180, 180, 180)
    # Camera body
    draw.rectangle([width//4, height//3, 3*width//4, 2*height//3], outline=camera_color, width=2)
    # Camera lens
    draw.ellipse([width//3, 2*height//5, 2*width//3, 3*height//5], outline=camera_color, width=2)
    
    # Save the image
    image.save('static/images/placeholder.jpg', 'JPEG', quality=95)
    print("Placeholder image created successfully!")

if __name__ == "__main__":
    create_placeholder_image() 