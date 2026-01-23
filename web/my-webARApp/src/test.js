const allPaths = [
  "parent_folder/folder_0/file.glb",
  "parent_folder/folder_0/pos.txt",
  "parent_folder/folder_1/pos.txt",
  "parent_folder/folder_1/file.glb",
];

let fileList = [];
let ptr_1 = 0;
let ptr_2 = allPaths.length - 1;

while (allPaths.length > 0) {
  if (ptr_1 == ptr_2) {
    break;
  }
  let currentPath = allPaths[ptr_1];
  if (allPaths[ptr_2].includes(currentPath.split("/")[1])) {
    fileList.push([allPaths[ptr_1], allPaths[ptr_2]]);
    allPaths.splice(ptr_2, 1);
    allPaths.splice(ptr_1, 1);
    ptr_1 = 0;
    ptr_2 = allPaths.length - 1;
  } else {
    ptr_1 += 1;
  }
}
console.log(fileList);
