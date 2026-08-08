import os
import re

TARGET_DIRS = [
    r"c:\workspace\Agent\seple-tender-platform\web\src",
    r"c:\workspace\Agent\seple-tender-platform\ui-tui\src"
]
EXTENSIONS = {".tsx", ".ts", ".js", ".json", ".css", ".md"}

def process_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        original_content = content
        
        # Replace standalone Hermes with Seple T Agent
        content = re.sub(r'(?<![a-zA-Z0-9_\-])Hermes(?![a-zA-Z0-9_])', 'Seple T Agent', content)
        
        # Replace standalone Nous with Novaedge
        content = re.sub(r'(?<![a-zA-Z0-9_\-])Nous(?![a-zA-Z0-9_])', 'Novaedge', content)
        
        if content != original_content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Updated: {filepath}")
            
    except Exception as e:
        print(f"Error processing {filepath}: {e}")

def main():
    for target_dir in TARGET_DIRS:
        if not os.path.exists(target_dir):
            continue
            
        for root, _, files in os.walk(target_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in EXTENSIONS:
                    filepath = os.path.join(root, file)
                    process_file(filepath)

if __name__ == "__main__":
    main()
