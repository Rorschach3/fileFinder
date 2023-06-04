from tqdm import tqdm
import os
import shutil
import time
import tkinter as tk
from tkinter import ttk
from tkinter.filedialog import askdirectory

# Create Tkinter root window
root = tk.Tk()
root.ttk.title("")
root.filename = askdirectory(
    initialdir="/mnt/f",
    title="Choose a directory to process"
)
root.withdraw()  # Hide the root window


extensions = (".ttf", ".otf", ".woff", ".woff2", ".fnt", ".svg", ".eot")
# Prompt user to input directory, extension, and output location
dir_path = root.filename
extension = extensions
output_path = askdirectory(
    initialdir="/mnt/f",
    title="Choose a directory to save the output"
)

# Iterate through all files and directories within the input directory
for root, dirs, files in os.walk(dir_path):
    with tqdm(total=len(files)) as pbar:
        for file in files:
            # Check if file has the specified extension
            if file.endswith(extension):
                # Construct full path of file and output location
                file_path = os.path.join(root, file)
                output_file_path = os.path.join(output_path, file)
                # Copy file to output location
                shutil.copy(file_path, output_file_path)
                print(f"Copied {file_path} to {output_file_path}")
            pbar.update(1)
    print(f"Processing completed for directory: {root}")
