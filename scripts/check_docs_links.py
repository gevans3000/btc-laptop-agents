import os
import re
from pathlib import Path

def check_links():
    md_files = list(Path('.').rglob('*.md'))
    broken_count = 0
    
    for md_file in md_files:
        if '.venv' in str(md_file) or '.git' in str(md_file):
            continue
            
        content = md_file.read_text(encoding='utf-8')
        # Match [label](path) where path is not a URL
        links = re.findall(r'\[.*?\]\(((?!http|mailto|#).*?)\)', content)
        
        for link in links:
            # Remove anchors
            clean_link = link.split('#')[0].strip()
            if not clean_link:
                continue
                
            # Resolve relative path
            target_path = (md_file.parent / clean_link).resolve()
            
            if not target_path.exists():
                print(f"✗ Broken link in {md_file}: {link}")
                broken_count += 1
                
    if broken_count == 0:
        print("✓ All internal documentation links are valid.")
    else:
        print(f"FAILED: Found {broken_count} broken links.")

if __name__ == "__main__":
    check_links()
