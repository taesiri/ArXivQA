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
from datasets import load_dataset


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


def df_to_markdown(df, paper_id, arxiv_helper):
    paper_title, _ = arxiv_helper.fetch_paper_details(paper_id)
    # remove new lines from title
    paper_title = paper_title.replace("\n", " ").replace("\r", "")

    markdown_lines = [f"# [{paper_title}](https://arxiv.org/abs/{paper_id})"]
    for _, row in df.iterrows():
        markdown_lines.extend(
            ["\n## " + row["question"], "\n" + str(row["answer"]) + "\n"]
        )

    os.makedirs("./papers", exist_ok=True)
    with open(f"./papers/{paper_id}.md", "w") as md_file:
        md_file.write("\n".join(markdown_lines))


def create_parent_md(
    paper_ids,
    arxiv_helper,
    main_output_file="./README.md",
    header_file="HF/HEADER.md",
    new_readme_file="HF/README.md",
):
    print("Creating parent markdown file...")
    # Fetch and sort the paper details
    paper_details = [
        (pid, *arxiv_helper.fetch_paper_details(pid))
        for pid in tqdm(paper_ids, desc="Fetching paper details", ncols=100)
    ]
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

    # Create the main README.md content
    main_lines = [
        "# Automated Question Answering with ArXiv Papers\n",
        "\n## Latest 25 Papers\n",
    ]
    # Add the latest 25 papers to the main README
    for paper_id, title, _ in paper_details[:25]:
        arxiv_link = f"https://arxiv.org/abs/{paper_id}"
        md_link = f"https://github.com/taesiri/ArXivQA/blob/main/papers/{paper_id}.md"
        main_lines.append(f"- {title} - [[Arxiv]({arxiv_link})] [[QA]({md_link})]\n")

    main_lines.append("\n## List of Papers by Year\n")
    for year in sorted(yearly_data.keys(), reverse=True):
        main_lines.append(
            f"- [Papers for {year}](https://github.com/taesiri/ArXivQA/blob/main/Papers-{year}.md)\n"
        )

    # Acknowledgements section with link
    main_lines += [
        "\n## Acknowledgements\n",
        "This project is made possible through the generous support of ",
        "[Anthropic](https://www.anthropic.com/), who provided free access to the `Claude-2.1` API.\n",
    ]

    # Write to the original README.md file
    with open(main_output_file, "w") as md_file:
        md_file.writelines(main_lines)

    # Read the header content from HF/HEADER.md
    with open(header_file, "r") as file:
        header_content = file.read()

    # Combine header content with main_lines for the new README
    readme_content = header_content + "\n" + "\n".join(main_lines)

    # Write to the new README.md file in the HF directory
    with open(new_readme_file, "w") as md_file:
        md_file.write(readme_content)


def get_missing_paper_ids_from_cache(paper_ids, cache_db):
    """Return paper_ids that are not in the cache."""
    missing_ids = []
    for pid in tqdm(paper_ids, desc="Checking cache for missing papers"):
        if not cache_db.get(pid.encode()):
            missing_ids.append(pid)
    return missing_ids


def generate_readme():
    arxiv_dataset = load_dataset("taesiri/arxiv_qa")
    arxiv_dataset = arxiv_dataset["train"]
    paper_ids_raw = list(set(arxiv_dataset["paper_id"]))
    print(f"Total number of papers: {len(paper_ids_raw)}")
    # all paper ids must be 10 characters long, if not add trailing zeros
    # if the paper starts with 21,22,23 to shuld be 10 characters long
    # otherwise it should be 9

    paper_ids = []
    pid_mapper = {}

    for pid in paper_ids_raw:
        if pid.startswith("21") or pid.startswith("22") or pid.startswith("23"):
            # make sure it is 10 characters long, or add 0 to the end
            padded_zero = (10 - len(pid)) * "0"
            paper_ids.append(pid + padded_zero)
            pid_mapper[pid + padded_zero] = pid
        else:
            # make sure it is 9 characters long, or add 0 to the end
            padded_zero = (9 - len(pid)) * "0"
            paper_ids.append(pid + padded_zero)
            pid_mapper[pid + padded_zero] = pid

    arxiv_helper = ArxivHelper()

    # Check which paper_ids are missing from the cache
    missing_paper_ids = get_missing_paper_ids_from_cache(
        paper_ids, arxiv_helper.cache_db
    )
    print(len(missing_paper_ids), "papers are missing from the cache.")

    # Fetch details only for missing papers with a wait time every 50 requests
    for i, pid in enumerate(
        tqdm(missing_paper_ids, desc="Fetching missing paper details", ncols=100)
    ):
        time.sleep(3)  # Sleep for 2 minutes
        try:
            arxiv_helper.fetch_paper_details(pid)
        except Exception as e:
            # bad paper or bad internet connection
            print(f"Error fetching paper details for {pid}: {e}")

    valid_paper_ids = []

    dataset_pandas = arxiv_dataset.to_pandas()

    # Generate markdown for all papers
    for pid in tqdm(paper_ids, desc="Generating Markdown", ncols=100):
        # skip if the paper is not cached
        if not arxiv_helper.cache_db.get(pid.encode()):
            continue
        else:
            valid_paper_ids.append(pid)

        # tdf = arxiv_dataset.filter(
        #     lambda x: x["paper_id"] == pid_mapper[pid]
        # ).to_pandas()

        tdf = dataset_pandas[dataset_pandas["paper_id"] == pid_mapper[pid]]

        df_to_markdown(tdf, pid, arxiv_helper)

    create_parent_md(valid_paper_ids, arxiv_helper)

    with open("paper_ids.txt", "w") as f:
        for pid in sorted(paper_ids):
            f.write(pid + "\n")


if __name__ == "__main__":
    generate_readme()
    # while True:
    #     try:
    #         generate_readme()
    #     except Exception as e:
    #         print(e)
    #     print("Sleeping for 1 hour...")
    #     time.sleep(60 * 60)
