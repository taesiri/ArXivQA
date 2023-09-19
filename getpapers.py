import re
import arxiv
from difflib import SequenceMatcher
from multiprocessing import Pool, cpu_count, Lock
import time
from tqdm import tqdm

SIMILARITY_THRESHOLD = 0.8

# Read the content of the file and extract potential titles
def read_and_extract_titles(file_path):
    with open(file_path, "r") as file:
        content_new = file.read()
    table_pattern = r"\|(.+?)\|(.+?)\|(.+?)\|"
    table_matches = re.findall(table_pattern, content_new)
    return [match[2].strip() for match in table_matches][2:]


def get_best_match_from_arxiv(title, max_results=500, retries=3, delay=5):
    """
    Search for papers on arXiv based on the title and return the title and ID of the best match.
    Introduce retries and delay to handle UnexpectedEmptyPageError.
    """
    for _ in range(retries):
        try:
            search = arxiv.Search(
                query=title,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )

            best_match_title = None
            best_match_id = None
            best_similarity = -1

            for result in search.results():
                current_title = result.title
                similarity = SequenceMatcher(None, title, current_title).ratio()

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_title = current_title
                    best_match_id = result.entry_id.split("/")[-1]

            return best_match_title, best_match_id, best_similarity

        except Exception as e:
            time.sleep(delay)  # Delay before retrying

    return None, None, 0  # Return default values if all retries fail


def process_titles(titles_chunk, lock):
    for title in titles_chunk:
        clean_title = re.sub(r"\[|\]\(.*\)", "", title).strip()
        arxiv_title, arxiv_id, best_similarity = get_best_match_from_arxiv(clean_title)
        
        if arxiv_title and best_similarity > SIMILARITY_THRESHOLD:
            print(f"Accepted: {clean_title} -> {arxiv_title}")
            with lock:
                with open("matched_arxiv_ids.txt", "a") as file:  # Open in append mode
                    file.write(arxiv_id + "\n")
        elif arxiv_title:
            print(f"Rejected: {clean_title} -> {arxiv_title}")


from multiprocessing import Manager

def process_chunk_with_lock(args):
    chunk, lock = args
    return process_titles(chunk, lock)

if __name__ == "__main__":
    # Extract titles from the file
    titles = read_and_extract_titles("./papers.md")

    # Split the titles into chunks for parallel processing
    num_processes = 10
    chunk_size = len(titles) // num_processes
    title_chunks = [
        titles[i : i + chunk_size] for i in range(0, len(titles), chunk_size)
    ]

    # Create a manager for multiprocessing and a lock for file writing
    with Manager() as manager:
        lock = manager.Lock()

        # Ensure the file is empty before starting (optional, but avoids appending to any existing data)
        with open("matched_arxiv_ids.txt", "w") as file:
            pass

        # Use multiprocessing to process titles in parallel
        with Pool(processes=num_processes) as pool:
            list(tqdm(pool.imap(process_chunk_with_lock, [(chunk, lock) for chunk in title_chunks]), total=len(title_chunks)))
