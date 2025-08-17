import json
from bs4 import BeautifulSoup

INPUT_HTML = "messages.html"
OUTPUT_MD = "messages.md"
OUTPUT_JSONL = "messages.jsonl"

def get_text(element):
    """Safely gets stripped text from a BeautifulSoup element."""
    return element.get_text(" ", strip=True) if element else ""

def main():
    """
    Parses a Telegram chat history HTML file and converts it into Markdown
    and JSONL formats suitable for RAG applications.
    """
    try:
        with open(INPUT_HTML, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "lxml")
    except FileNotFoundError:
        print(f"Error: Input file not found at '{INPUT_HTML}'")
        return
    except Exception as e:
        print(f"Error reading or parsing HTML file: {e}")
        return

    items = []
    message_elements = soup.select("div.message-list-item")

    for msg in message_elements:
        message_id = msg.get("data-message-id")
        
        sender_name = ""
        # More robust sender selection logic
        sender_element = msg.select_one(".sender-title, .from_name")
        if sender_element:
            sender_name = get_text(sender_element)

        time_str = get_text(msg.select_one(".message-time, .date"))
        
        text_content = get_text(msg.select_one(".text-content, .text"))

        if not text_content:
            continue

        items.append({
            "message_id": message_id,
            "sender": sender_name,
            "time": time_str,
            "text": text_content
        })

    # Save to Markdown
    try:
        with open(OUTPUT_MD, "w", encoding="utf-8") as f:
            for item in items:
                f.write(f"[{item['time']}] {item['sender']}: {item['text']}\n")
    except IOError as e:
        print(f"Error writing to Markdown file '{OUTPUT_MD}': {e}")


    # Save to JSONL
    try:
        with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
            for item in items:
                record = {
                    "content": f"{item['sender']}: {item['text']}",
                    "metadata": {
                        "message_id": item["message_id"],
                        "sender": item["sender"],
                        "time": item["time"],
                        "source": "telegram_html_export"
                    }
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except IOError as e:
        print(f"Error writing to JSONL file '{OUTPUT_JSONL}': {e}")


    print(f"Conversion complete.")
    print(f"Processed {len(items)} messages.")
    print(f"Markdown file saved to: '{OUTPUT_MD}'")
    print(f"JSONL file saved to: '{OUTPUT_JSONL}'")

if __name__ == "__main__":
    main()
