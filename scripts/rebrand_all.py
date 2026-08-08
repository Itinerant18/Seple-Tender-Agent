import os
import re

TARGET_DIRS = [
    r"c:\workspace\Agent\seple-tender-platform\website",
    r"c:\workspace\Agent\seple-tender-platform\web",
    r"c:\workspace\Agent\seple-tender-platform\ui-tui",
    r"c:\workspace\Agent\seple-tender-platform\docs"
]
EXCLUDE_DIRS = {".docusaurus", "build", "node_modules", ".git", "dist", ".venv", "__pycache__"}
EXTENSIONS = {".md", ".mdx", ".tsx", ".ts", ".js", ".json", ".css", ".svg", ".html"}

def process_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        original_content = content
        
        # Replace Hermes Agent
        content = re.sub(r'(?i)hermes agent', 'Seple T Agent', content)
        
        # Replace Hermes
        content = re.sub(r'(?i)(?<!-)\bhermes\b(?!-)', 'Seple T Agent', content)
        
        # Replace Nous Research
        content = re.sub(r'(?i)nous research', 'Novaedge', content)
        
        # Replace NousResearch
        content = re.sub(r'(?i)nousresearch', 'Novaedge', content)
        
        if content != original_content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Updated: {filepath}")
            
    except Exception as e:
        pass

def main():
    for target_dir in TARGET_DIRS:
        if not os.path.exists(target_dir):
            continue
            
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in EXTENSIONS:
                    filepath = os.path.join(root, file)
                    process_file(filepath)

if __name__ == "__main__":
    main()
