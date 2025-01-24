FACT_CLEAN = "The cat jumped nimbly from the table to the chair, landing with elegance in front of the open window in the living room How did the cat land"
FACT_CORRUPTED = FACT_CLEAN.replace("elegance", "clumsiness")
END = "The cat landed with"
SPECIFIC_TOKENS = ["elegance", "clumsiness"]

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import torch as th
from mingpt.model import GPT
from mingpt.bpe import BPETokenizer
import torch.nn.functional as F
from mingpt.utils import set_seed

def get_specific_token_probs(logits, tokenizer, tokens):
    """Get probabilities of specific tokens from logits."""
    probs = F.softmax(logits, dim=-1)
    
    # Tokenize each token and get all subword token IDs
    token_ids_list = [tokenizer(token) for token in tokens]
    
    # Calculate probabilities for each token
    token_probs = {}
    for token, token_ids in zip(tokens, token_ids_list):
        # Sum probabilities for all subword token IDs
        token_probs[token] = sum(probs[0, token_id].item() for token_id in token_ids)
    
    return token_probs

def generate_heatmap(model_type, diff_matrix, tokens, specific_token):
    plt.figure(figsize=(30, 16))
    sns.heatmap(diff_matrix,
                cmap='crest',
                annot=True,
                xticklabels=tokens)
    plt.xticks(rotation=45, ha='right')
    plt.xlabel('Token')
    plt.ylabel('Layer')
    plt.title(f"Patching Heatmap of '{specific_token}' Token in the Corrupted Input")
    plt.tight_layout()
    plt.savefig(f'patching_heatmap_{model_type}_{specific_token}.png')
    plt.close()

def tokenize_and_print(tokenizer, text, device):
    tokens = tokenizer(text).to(device)
    tokens_str = [tokenizer.decode(th.tensor([token])) for token in tokens[0]]
    print("Detokenized input as strings: " + '/'.join(tokens_str))
    return tokens

# Initialization
device = "mps" if th.backends.mps.is_available() else "cuda" if th.cuda.is_available() else "cpu"
print(f"Running on device: {device}")
model_type = "gpt2-medium"
seed = 78
set_seed(seed)

# Initialize model, tokenizer and input
model = GPT.from_pretrained(model_type)
model.to(device)
model.eval()
tokenizer = BPETokenizer()

# Tokenize inputs
clean = tokenize_and_print(tokenizer, FACT_CLEAN + END, device)
corrupted = tokenize_and_print(tokenizer, FACT_CORRUPTED + END, device)

# Get predictions for clean input
logits_clean, _ = model(clean, store_activations=True)
clean_activations = model.layer_activations.copy()
print("\nProbabilities for specific tokens in clean input:")
print(get_specific_token_probs(model.last_token_logits, tokenizer, SPECIFIC_TOKENS))
reference_logits = model.last_token_logits[0]

# Setup patching loop
n_layers = len(model.transformer.h)
print(f"Number of layers: {n_layers}")
seq_length = corrupted.size(1)
print(f"Sequence length: {seq_length}")

# Get tokens
tokens = [tokenizer.decode(th.tensor([corrupted[0, i].item()])) for i in range(seq_length)]

# Iterate through each specific token
for specific_token in SPECIFIC_TOKENS:
    diff_matrix = np.zeros((n_layers, seq_length))
    token_idx = tokenizer(specific_token)[0]
    
    # Iterate through layers and positions
    for layer in range(n_layers):
        for pos in range(seq_length):
            # Forward pass with patching
            logits_patched, _ = model(corrupted.to(device), 
                                    patch_params=(layer, pos, clean_activations[f'layer_{layer}'][:, pos, :]))
            
            # Convert logits to probabilities
            clean_probs = F.softmax(reference_logits, dim=-1)
            patched_probs = F.softmax(model.last_token_logits[0], dim=-1)
            
            # Compute probability difference
            diff_matrix[layer, pos] = patched_probs[token_idx].item() - clean_probs[token_idx].item()

    # Visualize results with token labels
    generate_heatmap(model_type, diff_matrix, tokens, specific_token)

# Get predictions for corrupted input
logits_corrupted, _ = model(corrupted.to(device), patch_params=(n_layers,seq_length, clean_activations[f'layer_{n_layers-1}'][:, seq_length-1, :]))
# Get top predictions for corrupted input
print("\nProbabilities for specific tokens in corrupted input:")
print(get_specific_token_probs(model.last_token_logits, tokenizer, SPECIFIC_TOKENS))