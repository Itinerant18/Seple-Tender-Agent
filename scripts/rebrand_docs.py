import os
import re

TARGET_DIR = r"c:\workspace\Agent\seple-tender-platform"
EXCLUDE_DIRS = {".docusaurus", "build", "node_modules", ".git", ".venv", "venv", "dist", ".pytest_cache", "graphify-out", "apps", "plugins", ".github"}
EXTENSIONS = {".md", ".mdx"}

def process_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        original_content = content
        
        # Replace "Hermes Agent" case-insensitively
        content = re.sub(r'(?i)hermes agent', 'Seple T Agent', content)
        
        # Replace "Hermes" case-insensitively but try to avoid URLs and code variables
        # Look for "Hermes" by itself with word boundaries, avoiding dashes (like hermes-agent)
        # We will just do a lookahead/lookbehind to ensure it's not part of a hyphenated word
        content = re.sub(r'(?i)(?<!-)\bhermes\b(?!-)', 'Seple T Agent', content)
        
        if content != original_content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Updated: {filepath}")
            
    except Exception as e:
        print(f"Failed to process {filepath}: {e}")

def main():
    for root, dirs, files in os.walk(TARGET_DIR):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in EXTENSIONS:
                filepath = os.path.join(root, file)
                process_file(filepath)

if __name__ == "__main__":
    main()
