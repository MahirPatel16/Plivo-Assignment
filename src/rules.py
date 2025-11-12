# src/rules.py
import re, json
from typing import List, Dict

# --- Helper Functions for Rules ---

def _load_misspell_map(path: str = "data/misspell_map.json") -> Dict[str, str]:
    """Loads the misspelling map from the data directory."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Misspell map not found at {path}. Skipping.")
        return {}

def _apply_misspell_map(text: str, misspell_map: Dict[str, str]) -> str:
    """Applies simple text replacements from the misspell map."""
    for k, v in misspell_map.items():
        text = re.sub(r'\b' + re.escape(k) + r'\b', v, text, flags=re.IGNORECASE)
    return text

def _apply_spoken_numbers(text: str) -> str:
    """
    Converts specific spoken number patterns, ADDING currency symbol.
    """
    # NEW: Added '₹' to the replacement string
    text = re.sub(r'nine nine nine', '₹999', text, flags=re.IGNORECASE)
    text = re.sub(r'nine double nine', '₹999', text, flags=re.IGNORECASE)
    return text

def _apply_email_fixes(text: str, names_lex: List[str]) -> str:
    """
    Fixes common ASR errors in email domains and adds dots
    between names (e.g., 'siddharthmehta' -> 'siddharth.mehta').
    Emails are forced to lowercase.
    """
    # 1. Fix domain endings (e.g., gmailcom -> gmail.com)
    text = re.sub(r'@(\w+)(com|net|org)\b', r'@\1.\2', text, flags=re.IGNORECASE)
    
    # [cite_start]2. Add dot between (firstname)mehta based on lexicon [cite: 1, 2, 3, 4, 5]
    name_set = set(n.lower() for n in names_lex)
    
    def _split_mehta_email(match: re.Match) -> str:
        username = match.group(1) # e.g., 'siddharthmehta'
        domain = match.group(2)   # e.g., 'gmail.com'
        
        if username.lower().endswith('mehta'):
            first_part = username[:-5] # e.g., 'siddharth'
            if first_part.lower() in name_set:
                # It's a match! Force to lowercase as requested.
                return f"{first_part}.mehta@{domain}".lower()
        
        # No match, but still force to lowercase.
        return match.group(0).lower()
    
    # Find (username)@(domain)
    text = re.sub(r'\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b', 
                  _split_mehta_email, text, flags=re.IGNORECASE)
    
    return text

def _format_indian_currency(match: re.Match) -> str:
    """Callback to format a number string into Indian numbering."""
    symbol = match.group(1)  # '₹'
    number_str = match.group(2)
    
    if not number_str:
        return match.group(0)
    
    # Remove any existing commas
    number_str = number_str.replace(',', '')
    
    l = len(number_str)
    if l <= 3:
        return f"{symbol}{number_str}"
    
    # Indian grouping: last 3 digits, then groups of 2 from right to left
    last_three = number_str[-3:]
    rest = number_str[:-3]
    
    # Build groups of 2 from right to left
    groups = []
    while rest:
        if len(rest) <= 2:
            groups.insert(0, rest)
            break
        else:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
    
    # Join all groups with commas
    if groups:
        formatted = ','.join(groups) + ',' + last_three
    else:
        formatted = last_three
    
    return f"{symbol}{formatted}"

def _apply_indian_currency_format(text: str) -> str:
    """Finds all instances of ₹[digits] and applies Indian grouping."""
    text = re.sub(r'(₹)(\d{4,})', _format_indian_currency, text)
    return text

# --- Main Candidate Generation Function ---

def generate_candidates(text: str, names_lex: List[str]) -> List[str]:
    """
    Generates candidates for the ranker (original + 1 corrected).
    """
    misspell_map = _load_misspell_map()
    
    cand = text
    cand = _apply_misspell_map(cand, misspell_map)
    cand = _apply_spoken_numbers(cand)
    cand = _apply_name_capitalization(cand, names_lex)
    cand = _apply_email_fixes(cand, names_lex) 
    cand = _apply_indian_currency_format(cand)
    
    if cand == text:
        return [text]
    else:
        return [text, cand]

def _apply_name_capitalization(text: str, names_lex: List[str]) -> str:
    """Capitalizes names found in the lexicon."""
    for name in names_lex:
        text = re.sub(r'\b' + re.escape(name) + r'\b', name, text, flags=re.IGNORECASE)
    return text

# --- Main Candidate Generation Function ---
def add_punctuation(text: str) -> str:
    """Add basic punctuation to the text"""
    text = text.strip()
    
    # Don't add if already ends with punctuation
    if text and text[-1] in '.?!':
        return text
    
    # Add question mark for questions
    lower = text.lower()
    question_starts = ['can', 'could', 'would', 'should', 'will', 'is', 'are', 'do', 'does', 'did', 'hi', 'hello']
    
    first_word = lower.split()[0] if lower.split() else ''
    if first_word in question_starts or 'can you' in lower or 'can we' in lower:
        return text + '?'
    
    # Add period for statements
    return text + '.'