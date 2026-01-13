# AR-Explorer
Trying to exlplore Apples ARKit and seeing if an LLM can put together a world from a list of objects

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


# Issues that I had
## Problems with the VM:



# Running the server:
- From repo root, set up Python deps (ideally in a venv): python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r
   requirements.txt && pip install fastapi uvicorn pydantic requests.
- Start Ollama locally and ensure the TinyLlama model is installed (ollama pull tinyllama:latest); set any overrides like OLLAMA_MODEL if you don’t want the
   default. Also export PINECONE_API_KEY and have an index named objaverse-index ready (needed by main.py), and optionally make sure Apple’s usdzconvert is on
   PATH if you want USDZ output.
- Run the API: uvicorn server:app --host 0.0.0.0 --port 8000 (run this in the repo directory so server.py can locate main.py).
- Verify readiness: curl http://localhost:8000/health (returns 200 only if Ollama + model are reachable).
- Generate: curl -X POST http://localhost:8000/generate -H "Content-Type: application/json" -d '{"prompt":"your scene prompt"}' -o assets_bundle.zip (or GET
   with ?prompt=...); it streams back the zip created by main.py.

# Running on IOS Build via localHost
• Use the Mac’s IP instead of localhost and let uvicorn listen on all interfaces so the iPad can reach it.

  - Start the API on the Mac with a public bind: uvicorn server:app --host 0.0.0.0 --port 8000.
  - Find the Mac’s Wi‑Fi IP: ipconfig getifaddr en0 (e.g., 192.168.1.23). Both devices must be on the same network and the Mac firewall must allow inbound
    8000.
  - In AppleARKit/LLMVerse/LLMVerse/ContentView.swift, change the URL to that IP, e.g.:

    let baseURL = "http://192.168.1.23:8000"
    let request = AF.download("\(baseURL)/generate", parameters: ["prompt": prompt], to: { ... })
  - Add ATS/Local Network allowances in Info.plist for the IP while developing:
      - NSAppTransportSecurity → NSAllowsArbitraryLoads = YES (or an exception domain for the IP).
      - NSLocalNetworkUsageDescription with a short reason.
  - Sanity check from the iPad browser: http://192.168.1.23:8000/health should return JSON; if not, fix firewall/bind/IP first.

  Note: once connectivity works, adjust the unzip logic—your zip contains nested parent_folder/folder_n directories and pos.txt is JSON like [x,y,z], so the
  current flat directory scan and comma-split won’t load anchors.