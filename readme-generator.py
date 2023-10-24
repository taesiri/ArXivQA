import os
import pickle
import time
import git
import pandas as pd
import requests
import rocksdb
from bs4 import BeautifulSoup
from datetime import datetime
from tqdm import tqdm


class ArxivHelper:
    ARXIV_API_ENDPOINT = "http://export.arxiv.org/api/query?id_list={}"

    def __init__(self):
        self.cache_db = rocksdb.DB(
            "arxiv_cache_rockdb", rocksdb.Options(create_if_missing=True)
        )

    def fetch_paper_details(self, paper_id):
        # First, try to fetch from cache
        cached_data_bytes = self.cache_db.get(paper_id.encode())
        if cached_data_bytes:
            title, pub_date_str = pickle.loads(
                cached_data_bytes
            )  # Deserialize with pickle
            pub_date = datetime.fromisoformat(
                pub_date_str
            )  # Convert string back to datetime
            return title, pub_date

        # If not in cache, fetch details from Arxiv
        response = requests.get(self.ARXIV_API_ENDPOINT.format(paper_id))
        response.raise_for_status()
        xml_content = response.content.decode("utf-8")
        title = self._extract_from_xml(xml_content, "title")
        date_str = self._extract_from_xml(xml_content, "published")
        pub_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")

        # Save to cache and return
        self.cache_db.put(
            paper_id.encode(), pickle.dumps((title, pub_date.isoformat()))
        )
        return title, pub_date

    def _extract_from_xml(self, xml_content, tag):
        start_idx = xml_content.find(f"<{tag}>") + len(tag) + 2
        end_idx = xml_content.find(f"</{tag}>", start_idx)
        return xml_content[start_idx:end_idx].strip()


def get_paper_ids_from_repo(repo_path):
    # Get the list of CSV files in the papers directory of the cloned repository
    csv_files = [
        filename
        for filename in os.listdir(os.path.join(repo_path, "papers"))
        if filename.endswith(".csv")
    ]

    # Extract paper IDs from filenames
    paper_ids = [filename.replace(".csv", "") for filename in csv_files]

    # Extract base IDs and ensure only one version of each paper is included
    base_ids = {paper_id.split("v")[0] for paper_id in paper_ids}
    unique_paper_ids = []
    for base_id in base_ids:
        versions = [pid for pid in paper_ids if pid.startswith(base_id)]
        unique_paper_ids.append(sorted(versions)[0])  # Add the earliest version

    return unique_paper_ids


def csv_to_markdown(paper_id, repo_path, arxiv_helper):
    df_path = os.path.join(repo_path, "papers", f"{paper_id}.csv")
    if not os.path.exists(df_path):
        print(f"No CSV found for paper ID: {paper_id}")
        return

    df = pd.read_csv(df_path)
    paper_title, _ = arxiv_helper.fetch_paper_details(paper_id)

    markdown_lines = [f"# [{paper_title}](https://arxiv.org/abs/{paper_id})"]
    for _, row in df.iterrows():
        markdown_lines.extend(
            ["\n## " + row["question"], "\n" + str(row["answer"]) + "\n"]
        )

    os.makedirs("./papers", exist_ok=True)
    with open(f"./papers/{paper_id}.md", "w") as md_file:
        md_file.write("\n".join(markdown_lines))


def create_parent_md(paper_ids, arxiv_helper, main_output_file="./README.md"):
    paper_details = [(pid, *arxiv_helper.fetch_paper_details(pid)) for pid in tqdm(paper_ids, desc="Fetching paper details", ncols=100)]
    paper_details.sort(key=lambda x: x[2], reverse=True)  # Sort by publication date
    
    yearly_data = {}
    for paper_id, title, pub_date in paper_details:
        year = pub_date.strftime("%Y")
        month_name = pub_date.strftime("%B")

        arxiv_link = f"https://arxiv.org/abs/{paper_id}"
        md_link = f"https://github.com/taesiri/ArXivQA/blob/main/papers/{paper_id}.md"
        title = title.replace("\n", " ").replace("\r", "")
        line = f"- {title} - [[Arxiv]({arxiv_link})] [[QA]({md_link})]\n"
        
        if year not in yearly_data:
            yearly_data[year] = {"content": [], "months": set()}
        
        if month_name not in yearly_data[year]["months"]:
            yearly_data[year]["content"].append(f"\n### {month_name} {year}\n")
            yearly_data[year]["months"].add(month_name)
        
        yearly_data[year]["content"].append(line)

    # Save the yearly markdown files
    for year, data in yearly_data.items():
        with open(f"Papers-{year}.md", "w") as md_file:
            md_file.writelines(data["content"])

    # Create the main README.md with the desired structure
    main_lines = [
        "# Automated Question Answering with ArXiv Papers\n",
        "\n## Latest 25 Papers\n"
    ]
    # Add the latest 25 papers to the main README
    for paper_id, title, _ in paper_details[:25]:
        arxiv_link = f"https://arxiv.org/abs/{paper_id}"
        md_link = f"https://github.com/taesiri/ArXivQA/blob/main/papers/{paper_id}.md"
        main_lines.append(f"- {title} - [[Arxiv]({arxiv_link})] [[QA]({md_link})]\n")
    
    main_lines.append("\n## List of Papers by Year\n")
    for year in sorted(yearly_data.keys(), reverse=True):
        main_lines.append(f"- [Papers for {year}](Papers-{year}.md)\n")

    with open(main_output_file, "w") as md_file:
        md_file.writelines(main_lines)



def get_missing_paper_ids_from_cache(paper_ids, cache_db):
    """Return paper_ids that are not in the cache."""
    missing_ids = []
    for pid in tqdm(paper_ids, desc="Checking cache for missing papers"):
        if not cache_db.get(pid.encode()):
            missing_ids.append(pid)
    return missing_ids


# MAIN EXECUTION
REPO_URL = "https://huggingface.co/datasets/taesiri/arxiv_qa.git"
REPO_PATH = "./arxiv_qa_repo"
if not os.path.exists(REPO_PATH):
    git.Repo.clone_from(REPO_URL, REPO_PATH)
else:
    repo = git.Repo(REPO_PATH)
    repo.remotes.origin.pull()

paper_ids = get_paper_ids_from_repo(REPO_PATH)
arxiv_helper = ArxivHelper()

# Check which paper_ids are missing from the cache
missing_paper_ids = get_missing_paper_ids_from_cache(paper_ids, arxiv_helper.cache_db)
print(len(missing_paper_ids), "papers are missing from the cache.")

# Fetch details only for missing papers with a wait time every 50 requests
for i, pid in enumerate(
    tqdm(missing_paper_ids, desc="Fetching missing paper details", ncols=100)
):
    time.sleep(3)  # Sleep for 2 minutes
    arxiv_helper.fetch_paper_details(pid)

# Generate markdown for all papers
for pid in tqdm(paper_ids, desc="Generating Markdown", ncols=100):
    csv_to_markdown(pid, REPO_PATH, arxiv_helper)


create_parent_md(paper_ids, arxiv_helper)

with open("paper_ids.txt", "w") as f:
    for pid in sorted(paper_ids):
        f.write(pid + "\n")
