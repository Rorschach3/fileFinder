import os
import shutil
import tkinter as tk
from tkinter import filedialog
from tkinter.filedialog import askdirectory
from tqdm import tqdm


def create_duplicate_directory(output_directory):
    duplicate_directory = os.path.join(output_directory, "Duplicate Files")
    os.makedirs(duplicate_directory, exist_ok=True)
    return duplicate_directory


def process_files(start_directory, output_directory):
    duplicate_directory = create_duplicate_directory(output_directory)
    processed_files = 0
    non_duplicate_files = 0
    duplicate_files = 0

    # Traverse all directories and subdirectories
    for root, dirs, files in tqdm(os.walk(start_directory), desc="Processing files"):
        for file in files:
            file_path = os.path.join(root, file)
            destination_file_path = os.path.join(output_directory, file)

            # Check if the file already exists in the output directory
            if os.path.exists(destination_file_path):
                # Move the file to the duplicate directory
                shutil.move(file_path, os.path.join(duplicate_directory, file))
                duplicate_files += 1
            else:
                # Move the file to the output directory
                shutil.move(file_path, destination_file_path)
                non_duplicate_files += 1

            processed_files += 1

    # Print summary
    print("Processing completed!")
    print(f"Total files processed: {processed_files}")
    print(f"Non-duplicate files: {non_duplicate_files}")
    print(f"Duplicate files: {duplicate_files}")


# Create Tkinter root window
root = Tk()
root.title(askdirectory)
root.filename = filedialog.askopenfilename(initialdir="/", title="Choose a directory to process")
root.withdraw()  # Hide the root window


# Request user to select the starting directory using a folder selection dialog
start_directory = askdirectory(title="Select Starting Directory")


if not start_directory:
    print("No starting directory selected. Exiting...")
else:
    # Request user input for the output directory
    output_directory = input("Enter the output directory: ")


    # Call the function to process the files
    process_files(start_directory, output_directory)
