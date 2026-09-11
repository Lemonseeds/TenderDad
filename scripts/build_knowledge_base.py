import os
import re
import yaml
import pymupdf
from groq import Groq
from dotenv import load_dotenv

# Ensure we're in the right directory structure
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")

# Load environment variables
load_dotenv(os.path.join(BASE_DIR, ".env"))

def extract_text_from_pdf(pdf_path):
    doc = pymupdf.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    return text

def parse_projects_list(text):
    projects = []
    
    # We can split the text by "Area\n:\n" or similar, but a state machine or regex over the full text works well.
    # The structure generally repeats:
    # Client Name (1-2 lines)
    # Area
    # : <value>
    # Classification
    # : <value>
    # Area Description
    # : <value>
    
    # Let's split by "Area\n" and work backwards to find the client.
    # A robust regex based approach:
    # Match blocks that look like a project.
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        if lines[i] == "Area" and i > 0:
            client = lines[i-1]
            
            # Now extract Area, Classification, Area Description
            area_val = ""
            class_val = ""
            desc_val = ""
            
            # Area value
            if i + 1 < len(lines) and lines[i+1].startswith(":"):
                area_val = lines[i+1].lstrip(":").strip()
                i += 2
            elif i + 2 < len(lines) and lines[i+1] == ":" and not lines[i+2].startswith("Classification"):
                area_val = lines[i+2].strip()
                i += 3
            else:
                i += 1
                
            # Classification
            if i < len(lines) and lines[i] == "Classification":
                if i + 1 < len(lines) and lines[i+1].startswith(":"):
                    class_val = lines[i+1].lstrip(":").strip()
                    i += 2
                elif i + 2 < len(lines) and lines[i+1] == ":" and not lines[i+2].startswith("Area Description"):
                    class_val = lines[i+2].strip()
                    i += 3
                else:
                    i += 1
                    
            # Area Description
            if i < len(lines) and lines[i] == "Area Description":
                desc_lines = []
                if i + 1 < len(lines) and lines[i+1].startswith(":"):
                    desc_lines.append(lines[i+1].lstrip(":").strip())
                    i += 2
                elif i + 1 < len(lines) and lines[i+1] == ":":
                    i += 2
                else:
                    i += 1
                    
                while i < len(lines) and lines[i] != "Area" and lines[i] != "Classification" and "LIST OF PROJECTS" not in lines[i] and not lines[i].startswith("Web Site"):
                    desc_lines.append(lines[i])
                    i += 1
                desc_val = " ".join(desc_lines).strip()
                
            if client and (area_val or class_val or desc_val):
                projects.append({
                    "client": client,
                    "area": area_val,
                    "classification": class_val,
                    "description": desc_val
                })
        else:
            i += 1
            
    return projects

def extract_capabilities_from_brochure(text):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY not found in environment.")
        return []
        
    client = Groq(api_key=api_key)
    
    prompt = f"""You are analyzing a company brochure. Extract a bulleted list of atomic company capabilities.
Make them concise, standalone statements of what the company can do.
Return ONLY a valid JSON object with a single key 'capabilities' containing a list of strings, e.g. {{"capabilities": ["Capability 1", "Capability 2"]}}. Do NOT use markdown.

Brochure Text:
{text}"""
    
    print("Calling Groq API to extract capabilities...")
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"}
    )
    
    import json
    try:
        data = json.loads(response.choices[0].message.content)
        # Handle cases where the LLM might nest the list in an object
        if isinstance(data, dict):
            for key in data:
                if isinstance(data[key], list):
                    return data[key]
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"Failed to parse LLM output: {e}")
        return []
    
    return []

def main():
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    yaml_path = os.path.join(KNOWLEDGE_DIR, "capabilities.yaml")
    
    print("Parsing Axenic_List of Projects.pdf...")
    projects_pdf_path = os.path.join(DOCS_DIR, "Axenic_List of Projects.pdf")
    if os.path.exists(projects_pdf_path):
        projects_text = extract_text_from_pdf(projects_pdf_path)
        projects = parse_projects_list(projects_text)
        print(f"Extracted {len(projects)} projects.")
    else:
        print(f"File not found: {projects_pdf_path}")
        projects = []
        
    print("Extracting capabilities from Axenic Brochure.pdf...")
    brochure_pdf_path = os.path.join(DOCS_DIR, "Axenic Brochure.pdf")
    if os.path.exists(brochure_pdf_path):
        brochure_text = extract_text_from_pdf(brochure_pdf_path)
        capabilities = extract_capabilities_from_brochure(brochure_text)
        print(f"Extracted {len(capabilities)} capabilities.")
    else:
        print(f"File not found: {brochure_pdf_path}")
        capabilities = []
        
    data = {
        "capabilities": capabilities,
        "past_projects": projects
    }
    
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)
        
    print(f"Successfully wrote {yaml_path}")

if __name__ == "__main__":
    main()
