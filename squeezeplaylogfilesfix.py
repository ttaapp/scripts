import os
import re

def add_root_element(log_dir="./logs"):
    """Adds <data> root element to XML files, skipping those that already have it."""

    if not os.path.exists(log_dir):
        print(f"Error: Directory '{log_dir}' not found.")
        return

    for filename in os.listdir(log_dir):
        if filename.endswith(".xml"):
            filepath = os.path.join(log_dir, filename)
            try:
                with open(filepath, 'r') as f:
                    content = f.read()

                # Check if <data> root element already exists
                if re.search(r'<data\s*>', content, re.IGNORECASE):
                    print(f"Skipping {filename}: <data> root element already exists.")
                    continue  # Skip to the next file

                # Add <data> and </data>
                new_content = "<data>\n" + content + "\n</data>"

                with open(filepath, 'w') as f:
                    f.write(new_content)

                print(f"Added <data> root element to {filename}")

            except FileNotFoundError:
                print(f"Error: File '{filepath}' not found.")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    add_root_element()