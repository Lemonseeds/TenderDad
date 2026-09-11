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
    # Remove known header/footer garbage
    garbage = [
        "CLEANROOM PROJECTS & SERVICES",
        "LIST OF PROJECTS",
        "AXENIC SYSTEMS",
        "Web Site : www.cleanroomprojects.in; Email Add: axenicsystems@gmail.com",
        "Plot No.355/375, RSC37, Opp. Mumbai Bank, Gorai II, Borivali (west), Mumbai - 400 092",
        "Tel No. +91-9321325199 | 9321315182 | 9321305586",
        "DUVAL",
        "Enterprises Pvt Ltd",
        "Fabline (GENO Pharma) - Cleanroom Equipments"
    ]
    
    raw_lines = [line.strip() for line in text.split('\n') if line.strip()]
    lines = []
    for line in raw_lines:
        if line not in garbage:
            lines.append(line)
            
    projects = []
    current_proj = {}
    
    keywords = {"Area", "Classification", "Area Description"}
    rank = {"Area": 1, "Classification": 2, "Area Description": 3}
    
    i = 0
    while i < len(lines):
        is_keyword = False
        if lines[i] in keywords:
            if i + 1 < len(lines) and lines[i+1].startswith(":"):
                is_keyword = True
                
        if is_keyword:
            client_name = lines[i-1]
            if "client" not in current_proj:
                current_proj["client"] = client_name
            
            kw = lines[i]
            i += 1
            
            val_lines = []
            while i < len(lines):
                # Check if next line is a keyword
                next_is_keyword = False
                if lines[i] in keywords:
                    if i + 1 < len(lines) and lines[i+1].startswith(":"):
                        next_is_keyword = True
                if next_is_keyword:
                    break
                val_lines.append(lines[i])
                i += 1
                
            is_last = True
            if i < len(lines):
                next_kw = lines[i]
                if rank[next_kw] > rank[kw]:
                    is_last = False
            
            next_client = None
            if is_last and i < len(lines) and len(val_lines) > 0:
                next_client = val_lines.pop()
                
            val = " ".join(val_lines).strip()
            if val.startswith(":"):
                val = val[1:].strip()
                
            if kw == "Area": current_proj["area"] = val
            elif kw == "Classification": current_proj["classification"] = val
            elif kw == "Area Description": current_proj["description"] = val
            
            if is_last:
                projects.append(current_proj)
                current_proj = {}
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
