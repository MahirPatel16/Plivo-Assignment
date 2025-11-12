# src/postprocess_pipeline.py
import json, time, re
from typing import Dict, List
from .rules import generate_candidates, add_punctuation
from .ranker_onnx import PseudoLikelihoodRanker

class PostProcessor:
    def __init__(self, names_lex_path: str, onnx_model_path: str = None, device: str = "cpu", max_length: int = 64):
        self.names_lex = [x.strip() for x in open(names_lex_path, 'r', encoding='utf-8').read().splitlines() if x.strip()]
        self.ranker = PseudoLikelihoodRanker(onnx_path=onnx_model_path, device=device, max_length=max_length)

    def process_one(self, text: str) -> str:
        """Process a single utterance through candidate generation and ranking"""
        # Generate candidates
        cands = generate_candidates(text, self.names_lex)
        
        # Rank candidates
        best = self.ranker.choose_best(cands)
        
        # Add punctuation using smarter heuristics
        best = self._add_smart_punctuation(best)
        
        return best
    
    def _add_smart_punctuation(self, text: str) -> str:
        """Add appropriate punctuation based on sentence structure"""
        text = text.strip()
        
        # 1. Add periods before capitalized words (to split sentences)
        text = re.sub(r'(\S)\s+([A-Z][a-z]+)', r'\1. \2', text)

        # --- NEW RULES FOR INTRA-SENTENCE PUNCTUATION ---
        
        # 2. Add comma in lists, e.g., "...₹4,999 not ₹5,499"
        text = re.sub(r'(₹[0-9,]+)\s+(not\s+₹)', r'\1, \2', text, flags=re.IGNORECASE)
        
        # 3. Add colon after counter-offer, e.g., "Counter-offer from Kiran ₹2,799"
        text = re.sub(r'(Counter-offer from [A-Z][a-z]+)\s+(₹)', r'\1: \2', text)
        
        # 4. Add colon for "Original:", "Current price:", etc.
        text = re.sub(r'\b(Original|Current price)\s+(₹)', r'\1: \2', text, flags=re.IGNORECASE)

        # --- END NEW RULES ---

        # 5. Check for existing sentence-final punctuation
        if text and text[-1] in '.?!,;:':
            # But if it's just a comma, might need to change to period
            if text[-1] == ',':
                if not any(word in text.lower() for word in ['and', 'or', 'but']):
                    text = text[:-1] + '.'
            return text
        
        lower = text.lower()
        words = lower.split()
        
        if not words:
            return text + '.'
        
        # 6. Question patterns
        question_starters = [
            'can', 'could', 'would', 'should', 'will', 'shall', 'is', 'are', 
            'do', 'does', 'did', 'what', 'why', 'when', 'how', 'which'
        ]
        
        first_word = words[0]
        
        # Check for question
        if (first_word in question_starters or 
            'can you' in lower or 'can we' in lower or 
            'do you' in lower or 'will you' in lower or
            'should we' in lower or 'could you' in lower):
            return text + '?'
        
        # 7. Add commas after greeting names at start
        if len(words) > 1 and ',' not in text[:25]:
            # Pattern: "Hi Varun..." or "Hello Arnav..."
            if first_word in ['hi', 'hello', 'hey']:
                parts = text.split(None, 2)
                if len(parts) >= 3:
                    text = parts[0] + ' ' + parts[1] + ', ' + parts[2]
            
            # Pattern: "Ansh I'm offering..."
            elif words[0][0].isupper() and words[1].lower() not in ['and', 'or', 'is', 'was', 'at']:
                parts = text.split(None, 1)
                if len(parts) == 2:
                    text = parts[0] + ', ' + parts[1]
        
        # 8. Add colons before email addresses
        if '@' in text:
            # Pattern: "Reply at kiran.mehta..." -> "Reply at: kiran.mehta..."
            text = re.sub(r'\b(email|contact|reply|reach me at)\s+([a-z0-9])', 
                         r'\1: \2', text, flags=re.IGNORECASE)
            # Pattern: "confirm by email siddharth..." -> "confirm by email: siddharth..."
            text = re.sub(r'confirm by email\s', 'confirm by email: ', text, flags=re.IGNORECASE)

        # 9. Default: add period if no punctuation
        if text[-1] not in '.?!,;:':
            text = text + '.'
        
        return text

def run_file(input_path: str, output_path: str, names_lex_path: str, onnx_model_path: str = None, device: str = "cpu", max_length: int = 64):
    """Process a file of noisy transcripts"""
    pp = PostProcessor(names_lex_path, onnx_model_path=onnx_model_path, device=device, max_length=max_length)
    rows = [json.loads(line) for line in open(input_path, 'r', encoding='utf-8')]
    out = []
    for r in rows:
        pred = pp.process_one(r["text"])
        out.append({"id": r["id"], "text": pred})
    with open(output_path, 'w', encoding='utf-8') as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")