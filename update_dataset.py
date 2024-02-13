import git
import os
import pandas as pd
import pandas as pd
from glob import glob
from datasets import load_dataset, Dataset, DatasetDict
from tqdm import tqdm

REPO_URL = "https://huggingface.co/datasets/taesiri/arxiv_qa2"
REPO_PATH = "./arxiv_qa2"

if os.path.exists(REPO_PATH):
    print("Removing existing repo")
    os.system("rm -rf " + REPO_PATH)

git.Repo.clone_from(REPO_URL, REPO_PATH)

dfs = []

for f in tqdm(glob(REPO_PATH + "/papers/*/*.csv")):
    try:
        tdf = pd.read_csv(f)
        pid = f.split("/")[-1].replace(".csv", "")
        tdf["paper_id"] = pid
        dfs.append(tdf)
    except:
        print(f)

df = pd.concat(dfs, ignore_index=True)
df = df[~df["answer"].str.strip().str.startswith("Unfortunately")]

df = df.drop_duplicates(subset=["question", "answer"])
df = df.astype(str)

print(f"Total number of QA pairs: {len(df)}")
# total number of unique papers:
print(f"Total number of unique papers: {len(df['paper_id'].unique())}")

arxiv_qa_dataset = Dataset.from_pandas(df, preserve_index=False)
arxiv_qa_dataset.push_to_hub("taesiri/arxiv_qa")
