from tqdm import tqdm
import os
import shutil
import time

# prompt user to input directory, extension, and output location
dir_path = input("Enter directory location: ")
extension = input("Enter file extension to search for: ")
output_path = input("Enter output location: ")

# iterate through all files and directories within the input directory
for root, dirs, files in os.walk(dir_path):

    with tqdm(total=100) as pbar:
        for i in range(100):
            time.sleep(0.3)
            pbar.update(10)
            for file in files:
                # check if file has the specified extension
                if file.endswith(extension):
                    # construct full path of file and output location
                    file_path = os.path.join(root, file)
                    output_file_path = os.path.join(output_path, file)
                    # copy file to output location
                    tqdm(shutil.copy(file_path, output_file_path))
                    print(f"Copied {file_path} to {output_file_path}")
    print(f"File {file_path}: completed!")
