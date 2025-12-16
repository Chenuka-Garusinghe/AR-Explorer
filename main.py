import objaverse.xl as oxl
import pandas as pd
import os
import requests
from urllib.parse import urlparse
import ollama
import json
from zipfile import ZipFile
import random
from fastapi import HTTPException
import sys
from pinecone import Pinecone


ANNOTATION_CACHE = "data/objaverse_annotations"
OUTPUT_DIR = "data/my_objaverse_subset"  # change if you want a different folder
PER_SOURCE = 2  # objects per source; set to None to download everything (very large)
RANDOM_SEED = 0

annotations = oxl.get_annotations(download_dir=ANNOTATION_CACHE)
print(f"Loaded {len(annotations):,} annotations")

# Pick a subset to download.
if PER_SOURCE:
    objects_df = (
        annotations.groupby("source", group_keys=False)
        .apply(
            lambda df: df.sample(n=min(PER_SOURCE, len(df)), random_state=RANDOM_SEED)
        )
        .reset_index(drop=True)
    )
else:
    objects_df = annotations.copy()

print(f"Prepared {len(objects_df):,} objects to download")
objects_df.head()

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
pc = Pinecone(api_key=PINECONE_API_KEY)

# To get the unique host for an index,
# see https://docs.pinecone.io/guides/manage-data/target-an-index
index = pc.Index(name="objaverse-index")


def search_categories(query_text: str, top_k: int = 5):
    results = index.search(
        namespace="objaverse-namespace",
        query={"inputs": {"text": query_text}, "top_k": top_k},  # type: ignore
        fields=["category", "chunk_text"],
    )
    return results


user_prompt = (
    "Find 3–5 everyday household objects (e.g., kettle, coffee mug, desk lamp, backpack, office chair) suitable for an office desk scene."
)
search_results = search_categories(user_prompt, top_k=5)
hits = search_results.result["hits"]


def format_hits_for_llm(hits):
    lines = []
    for i, h in enumerate(hits):
        cat = h["fields"].get("category", "")
        text = h["fields"].get("chunk_text", "")
        lines.append(f"[{i}] category={cat}\n    chunk_text={text}")
    return "\n\n".join(lines)


def tinyllama_layout(user_prompt: str, hits):
    items_block = format_hits_for_llm(hits)

    prompt = f"""
You are a tool that selects relevant items and assigns 3D positions.

You MUST respond with JSON of exactly this form:

{{
  "layout": {{
    "0": [0.0, 0.05, -0.5],
    "2": [-0.5, 0.05, -0.8]
  }}
}}

Rules:
- "layout" must be a JSON object.
- Each key is a stringified integer index (e.g. "0", "1", "2", ...),
  referring to the indices in square brackets [] in the candidate list below.
- Each value is a JSON array [x, y, z] of floats (meters), suitable for model.position.
- Use only indices that appear in the candidate list.
- Use between 1 and 5 items maximum.
- Keep x and z in [-1.5, 1.5] and y in [0.0, 1.5].
- Do NOT include any other keys.
- Do NOT include explanations or text. Only the JSON object.

User query:
{user_prompt}

Candidates:
{items_block}
"""

    try:
        response = ollama.chat(
            model="tinyllama",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Always respond with JSON of the form "
                        '{"layout": {"<index>": [x, y, z], ...}} and nothing else.'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            format="json",
            options={"temperature": 0},
        )
    except:
        raise Exception("Error connecting to Ollama")

    content = response["message"]["content"]
    print("RAW LLM JSON:", content)  # for debugging

    data = json.loads(content)

    if not isinstance(data, dict) or "layout" not in data:
        raise ValueError(f"Unexpected JSON shape from LLM: {data}")

    layout_raw = data["layout"]
    if not isinstance(layout_raw, dict):
        raise ValueError(f"layout is not a dict: {layout_raw}")

    # Convert keys to ints and keep positions as lists
    positions_by_index = {}
    for k, pos in layout_raw.items():
        try:
            idx = int(k)
        except ValueError:
            continue  # skip weird keys

        # Basic sanity checks
        if (
            isinstance(pos, list)
            and len(pos) == 3
            and all(isinstance(v, (int, float)) for v in pos)
            and 0 <= idx < len(hits)
        ):
            positions_by_index[idx] = [float(pos[0]), float(pos[1]), float(pos[2])]

    return positions_by_index


# usage
positions_by_index = tinyllama_layout(user_prompt, hits)
print("Positions by index:", positions_by_index)


import requests

if "name" not in annotations.columns:
    annotations["name"] = (
        annotations["fileIdentifier"]
        .str.extract(r"/([^/]+?)(?:\.[a-zA-Z0-9]+)?$", expand=False)
        .fillna("")
    )

objects_to_display: dict = {}
for key in positions_by_index:
    obj_name = hits[key]["fields"]["category"]
    filtered_objects_data = annotations[
        annotations["name"].str.contains(obj_name, case=False, na=False)
    ]
    objects_to_display[key] = filtered_objects_data


finite_files = []
rows = []

for key, df in objects_to_display.items():
    df = df.iloc[:30].copy()
    df["pos_key"] = key
    rows.append(df)
    for _, row in df.iterrows():
        url = row["fileIdentifier"]

        try:
            head = requests.head(url, allow_redirects=True, timeout=5)
        except requests.RequestException as e:
            print("HEAD failed:", url, e)
            continue

        if head.status_code == 404:
            continue

        # convert GitHub "blob" URL to raw, oxl takes too long
        if (
            "github.com" in url
            and "/blob/" in url
            and "raw.githubusercontent.com" not in url
        ):
            url = url.replace("github.com/", "raw.githubusercontent.com/").replace(
                "/blob/", "/"
            )

        try:
            r = requests.get(url, stream=True, timeout=20)
            r.raise_for_status()
            finite_files.append(url)
        except requests.RequestException as e:
            print("GET failed:", url, e)
            continue

finite_annotations_df = pd.concat(rows, ignore_index=True)
finite_annotations_df = finite_annotations_df.drop_duplicates(subset=["fileIdentifier"])

def github_blob_to_raw(url: str) -> str:
    if "github.com" in url and "/blob/" in url:
        return url.replace("github.com/", "raw.githubusercontent.com/").replace("/blob/", "/")
    return url

download_dir = "./data/objaverse_found_custom"
os.makedirs(download_dir, exist_ok=True)

parent_folder = "parent_folder"
zip_path = os.path.join(download_dir, "assets_bundle.zip")

folder_n = 0

with ZipFile(zip_path, "w") as zf:
    # generate a pair of random numbers that is the length of positions_by_index apart
    fixed_distance = len(positions_by_index)
    num_a = int(random.uniform(0, fixed_distance))
    num_b = abs(fixed_distance - num_a)
    
    for _, row in finite_annotations_df.iloc[num_a:num_b].iterrows():
        url = github_blob_to_raw(row["fileIdentifier"])

        try:
            r = requests.get(url, stream=True, timeout=20)
            r.raise_for_status()
        except requests.RequestException as e:
            print("GET failed:", url, e)
            continue

        obj_filename = os.path.basename(urlparse(url).path)
        if not obj_filename.lower().endswith(".glb"):
            continue

        # Save the .glb locally (so ZipFile can write it)
        out_path_obj = os.path.join(download_dir, obj_filename)
        with open(out_path_obj, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

        # Write a per-object pos.txt (avoid overwriting)
        out_path_txt = os.path.join(download_dir, f"pos_{folder_n}.txt")
        pos_key = int(row["pos_key"])
        with open(out_path_txt, "w") as f_txt:
            f_txt.write(json.dumps(positions_by_index[pos_key]))

        # Put both into parent_folder/folder_n/ inside the zip
        folder_name = f"folder_{folder_n}"
        zf.write(out_path_obj, arcname=f"{parent_folder}/{folder_name}/{obj_filename}")
        zf.write(out_path_txt, arcname=f"{parent_folder}/{folder_name}/pos.txt")

        folder_n += 1
        
if folder_n == 0:
    if os.path.exists(zip_path):
        os.remove(zip_path)
    print("No .glb objects found; zip was not created.") 
    # Send 404 from this program
    raise HTTPException(status_code=400, detail="No folders found")
    sys.exit(1)
    
print("Created zip:", zip_path)

