import objaverse.xl as oxl
import argparse
import pandas as pd
import os
import requests
from urllib.parse import urlparse
import ollama
import json
from zipfile import ZipFile
from fastapi import HTTPException
import sys
from pinecone import Pinecone


ANNOTATION_CACHE = "data/objaverse_annotations"
OUTPUT_DIR = "data/my_objaverse_subset"  # change if you want a different folder
PER_SOURCE = 2  # objects per source; set to None to download everything (very large)
RANDOM_SEED = 0


def load_annotations():
    annotations = oxl.get_annotations(download_dir=ANNOTATION_CACHE)
    print(f"Loaded {len(annotations):,} annotations")
    return annotations


def prepare_subset(annotations: pd.DataFrame) -> pd.DataFrame:
    if PER_SOURCE:
        objects_df = (
            annotations.groupby("source", group_keys=False)
            .apply(
                lambda df: df.sample(
                    n=min(PER_SOURCE, len(df)), random_state=RANDOM_SEED
                )
            )
            .reset_index(drop=True)
        )
    else:
        objects_df = annotations.copy()

    print(f"Prepared {len(objects_df):,} objects to download")
    return objects_df


def init_pinecone():
    PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
    pc = Pinecone(api_key=PINECONE_API_KEY)
    # To get the unique host for an index,
    # see https://docs.pinecone.io/guides/manage-data/target-an-index
    return pc.Index(name="objaverse-index")


def search_categories(index, query_text: str, top_k: int = 5):
    results = index.search(
        namespace="objaverse-namespace",
        query={"inputs": {"text": query_text}, "top_k": top_k},  # type: ignore
        fields=["category", "chunk_text"],
    )
    return results


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
            model="tinyllama:latest",
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


def ensure_name_column(annotations: pd.DataFrame) -> pd.DataFrame:
    if "name" not in annotations.columns:
        annotations["name"] = (
            annotations["fileIdentifier"]
            .str.extract(r"/([^/]+?)(?:\.[a-zA-Z0-9]+)?$", expand=False)
            .fillna("")
        )
    print(f"Ensured 'name' column exists with {annotations['name'].notnull().sum():,} non-null entries")
    return annotations


def build_objects_to_display(annotations, hits, positions_by_index):
    objects_to_display: dict = {}
    for key in positions_by_index:
        obj_name = hits[key]["fields"]["category"]
        filtered_objects_data = annotations[
            annotations["name"].str.contains(obj_name, case=False, na=False, regex=False)
        ]
        objects_to_display[key] = filtered_objects_data
    return objects_to_display


def is_glb_identifier(identifier: str) -> bool:
    """
    Return True when the URL/path clearly points to a .glb asset.
    Uses only the path portion so query strings do not interfere.
    """
    try:
        return urlparse(str(identifier)).path.lower().endswith(".glb")
    except Exception:
        return False


def collect_finite_annotations(objects_to_display):
    rows = []

    for key, df in objects_to_display.items():
        glb_candidates = df[df["fileIdentifier"].apply(is_glb_identifier)]
        if glb_candidates.empty:
            continue

        # keep a small batch per position and remember which position it maps to
        glb_candidates = glb_candidates.iloc[:30].copy()
        glb_candidates["pos_key"] = key

        for _, row in glb_candidates.iterrows():
            url = github_blob_to_raw(row["fileIdentifier"])

            try:
                head = requests.head(url, allow_redirects=True, timeout=5)
                if head.status_code == 404:
                    continue
            except requests.RequestException as e:
                print("HEAD failed:", url, e)
                continue

            rows.append({**row.to_dict(), "fileIdentifier": url})

    finite_annotations_df = (
        pd.DataFrame(rows).drop_duplicates(subset=["fileIdentifier", "pos_key"])
        if rows
        else pd.DataFrame()
    )

    return finite_annotations_df


def github_blob_to_raw(url: str) -> str:
    if "github.com" in url and "/blob/" in url:
        return url.replace("github.com/", "raw.githubusercontent.com/").replace(
            "/blob/", "/"
        )
    return url


def download_and_zip(finite_annotations_df, positions_by_index):
    if finite_annotations_df.empty:
        print("No .glb candidates available after filtering.")
        raise HTTPException(status_code=400, detail="No .glb files found")

    download_dir = "./data/objaverse_found_custom"
    os.makedirs(download_dir, exist_ok=True)
    zip_dir = os.path.dirname(zip_path)
    if zip_dir:
        os.makedirs(zip_dir, exist_ok=True)

    parent_folder = "parent_folder"
    # zip_path = os.path.join(download_dir, "assets_bundle.zip")

    folder_n = 0

    rows_to_fetch = (
        finite_annotations_df.sample(frac=1, random_state=RANDOM_SEED)
        .groupby("pos_key", group_keys=False)
        .head(1)
    )

    with ZipFile(zip_path, "w") as zf:
        for _, row in rows_to_fetch.iterrows():
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
            zf.write(
                out_path_obj, arcname=f"{parent_folder}/{folder_name}/{obj_filename}"
            )
            zf.write(out_path_txt, arcname=f"{parent_folder}/{folder_name}/pos.txt")

            folder_n += 1

    if folder_n == 0:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        print("No .glb objects found; zip was not created.")
        # Send 404 from this program
        raise HTTPException(status_code=400, detail="No .glb files found")
        # sys.exit(1)

    print("Created zip:", zip_path)
    return zip_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--zip-path", required=True)
    args = parser.parse_args()
    
    global user_prompt
    user_prompt = args.prompt

    global zip_path
    zip_path = args.zip_path

    annotations = load_annotations()
    prepare_subset(annotations)

    index = init_pinecone()
    search_results = search_categories(index, user_prompt, top_k=5)
    hits = search_results.result["hits"]

    positions_by_index = tinyllama_layout(user_prompt, hits)
    print("Positions by index:", positions_by_index)

    annotations = ensure_name_column(annotations)
    objects_to_display = build_objects_to_display(annotations, hits, positions_by_index)
    finite_annotations_df = collect_finite_annotations(objects_to_display)
    download_and_zip(finite_annotations_df, positions_by_index)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
