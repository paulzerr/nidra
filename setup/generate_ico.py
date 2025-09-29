from PIL import Image
import os

def generate_ico(source_png_path, output_ico_path):
    """
    Generates a multi-resolution .ico file from a source PNG image.
    """
    img = Image.open(source_png_path)
    
    # Define the standard sizes for a .ico file
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Ensure the output directory exists
    output_dir = os.path.dirname(output_ico_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    img.save(output_ico_path, format='ICO', sizes=sizes)
    print(f"Generated {output_ico_path} from {source_png_path}")

if __name__ == "__main__":
    source_image = "NIDRA/nidra_gui/neutralino/resources/icons/appIcon.png"
    output_icon = "docs/logo.ico"
    generate_ico(source_image, output_icon)