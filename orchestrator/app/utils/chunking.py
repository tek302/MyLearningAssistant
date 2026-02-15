from typing import List


def _find_word_boundary(text: str, start: int, end: int) -> int:
    """Find last break point (space/punct) in [start, end] to avoid mid-word split."""
    for i in range(end - 1, start - 1, -1):
        if text[i] in " \n\t.,;:!?":
            return i + 1
    return end


def chunk_text(text: str, max_chars: int = 2000, overlap_chars: int = 200) -> List[str]:
    """
    Split text into chunks with overlap.
    Breaks at word boundaries to avoid mid-word truncation.
    
    Args:
        text: Text to chunk
        max_chars: Maximum characters per chunk
        overlap_chars: Number of characters to overlap between chunks
        
    Returns:
        List of text chunks
    """
    if not text:
        return []
    
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + max_chars
        
        if end >= len(text):
            # Last chunk
            chunks.append(text[start:])
            break
        
        # Try to break at a sentence boundary (period, newline, or space)
        # Look backwards from end for a good break point
        break_point = end
        for i in range(end, max(start, end - 200), -1):
            if text[i] in [".", "\n", "!", "?"]:
                break_point = i + 1
                break
            elif text[i] == " " and i < end - 50:  # Don't break too early
                break_point = i + 1
                break
        
        # Fallback: avoid mid-word break (e.g. "Finally" -> "tly")
        if break_point == end:
            break_point = _find_word_boundary(text, start, end)
        
        chunk = text[start:break_point].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start forward with overlap
        start = break_point - overlap_chars
        if start < 0:
            start = break_point
    
    return chunks

