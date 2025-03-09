import pandas as pd
import requests
df = pd.read_csv("hf://datasets/Heffernan-WPI-Lab/DrawEduMath/Data/DrawEduMath_QA.csv")
from datasets import load_dataset

dataset = load_dataset("Heffernan-WPI-Lab/DrawEduMath")
train_data=dataset['train']
print(train_data[0])
import os

save_dir = "DrawEduMath_Images"
os.makedirs(save_dir, exist_ok=True)

for i, row in enumerate(train_data):
    image_url = row["Image URL"]
    image_name = row["Image Name"]
    
    response = requests.get(image_url)
    with open(os.path.join(save_dir, image_name), "wb") as f:
        f.write(response.content)
print("Downloaded 10 images successfully.")