# AR Explorer
Pipeline for exploring Objaverse assets, indexing their labels, and generating novel 3D-aware views with Zero123-XL for AR scene prototyping.

## What’s Here
- `main.ipynb`: end-to-end notebook for pulling Objaverse/LVIS objects, cleaning the label metadata, and pushing embeddings to Pinecone.
- `objverseloader.py`: tiny script that fetches a few tagged objects (e.g., trees) to `data/objaverse_found/` from the docs, but this is in the ipynb.
- `main.py`: minimal Zero123-XL Diffusers sample (set your device and input image).
- `data/`: cached annotations and a trimmed `labels.json` ready for embedding/upload.

## Quickstart
1) **Create env & install deps**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install --upgrade git+https://github.com/huggingface/diffusers.git  # Zero123-XL support
   pip install -r requirements.txt
   ```
2) **Grab Zero123-XL weights** (requires Git LFS; ~7GB):
   ```bash
   git lfs install
   git clone https://huggingface.co/ashawkey/zero123-xl-diffusers
   ```
   The sample in `main.py` loads from `./zero123-xl-diffusers` using `device_map="mps"` for Apple; switch to `"cuda"` or `"cpu"` as needed.
3) **Objaverse subset**  
   - Run `main.ipynb` to download a small, category-filtered subset to `data/objaverse_found/` (adjust queries/limits in the notebook).  
   - For a quick CLI sample, run:
     ```bash
     python objverseloader.py
     ```
4) **Pinecone indexing**
   - Set `PINECONE_API_KEY` in your environment.  
   - Execute the “Upserting to PineCone DB” section of `main.ipynb` to embed and push `data/labels.json` using the `llama-text-embed-v2` model.
5) **Generate novel views**  
   - Replace the placeholder `input_img` in `main.py` with your own PIL image.  
   - Run `python main.py` to save a rendered view (default `view0.png`).

## Working with apple AR Kit:
I will start by creating the UI (Since ive never really used swift). For the UI, I just need to create a prompt box. Then I will attach a method to be called when the enter button is hit in the prompt box. 

Once the method is called we will invoke a function to call the LLM. I should get the LLM to search the Vector DB based on the prompt, so match the prompt to the `description` key in the data. So `TinyLlama-1.1B` will then return a list of `categories` (These are the actually ObjaVerse labels).

Once the mobile app recieves a list of objects we will need to load them from objaverse (can we do this in swift ? or will we have to request it from a cloud script). 

I will store each object recived on a folder locally called `/Scene_objects`. We then load each object to the AR session in the app. I will then include a `Done` button which when hit will delete the `/Scene_objects` and reset the prompt bar waiting for a new prompt.

## Notes
- Objaverse downloads are large; keep `PER_SOURCE` small while experimenting.
- Zero123-XL inference benefits from GPU/Apple M-series acceleration.
- If you change output locations, update the paths in the notebook/scripts accordingly.

