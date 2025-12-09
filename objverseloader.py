import objaverse
import objaverse.xl as oxl
import multiprocessing

annotations = objaverse.load_annotations()
processes = multiprocessing.cpu_count()

def has_tag(ann, tag_name: str) -> bool:
    return any(
        t.get("name", "").lower() == tag_name.lower()
        for t in ann.get("tags", [])
    )

tree_uids = [
    uid
    for uid, ann in annotations.items()
    if has_tag(ann, "tree")
]

subset_uids = tree_uids[:5]  # e.g. first 10 trees

objects = objaverse.load_objects(
    uids=subset_uids,
    download_processes=processes,
)

# objects: Dict[uid -> local .glb path]
for uid, path in list(objects.items())[:3]:
    print(uid, "->", path)